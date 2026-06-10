/**
 * Markdown preprocessing for CJK punctuation + delimiter compatibility.
 *
 * NOTE (2026-06-04): remark-parse v11 (micromark 4) correctly handles all CJK
 * punctuation adjacent to `**`/`*` delimiters. Regex space insertion was found
 * to BREAK valid bold (e.g. `」**` → `」 **` destroys the strong node).
 * This function is now a passthrough. The AST mode is preserved as a fallback.
 */

export type PreprocessMode = 'regex' | 'ast';

// ---------------------------------------------------------------------------
// Mode resolution
// ---------------------------------------------------------------------------

function resolveMode(): PreprocessMode {
  const raw = process.env.NEXT_PUBLIC_MD_PREPROCESS_MODE ?? 'regex';
  return raw === 'ast' ? 'ast' : 'regex';
}

const MODE: PreprocessMode = resolveMode();

// ---------------------------------------------------------------------------
// Protocol blocks — never touch these
// ---------------------------------------------------------------------------

const PROTOCOL_BLOCK_RE = /^\[(?:ROW_)?STATE_JSON\]|^\[HYP_CANDIDATE\]/;

// ---------------------------------------------------------------------------
// CJK punctuation character set
// ---------------------------------------------------------------------------

const CJK_PUNCT = '，。！？、；：）】」』（【「『';

function isCjkPunct(ch: string): boolean {
  return CJK_PUNCT.includes(ch);
}

// ---------------------------------------------------------------------------
// Strategy 1: Regex (default)
// ---------------------------------------------------------------------------

const RE_BEFORE_BOLD = new RegExp(`([${CJK_PUNCT}])\\*\\*`, 'g');
const RE_BEFORE_ITALIC = new RegExp(`([${CJK_PUNCT}])\\*(?!\\*)`, 'g');
const RE_AFTER_BOLD = new RegExp(`\\*\\*([${CJK_PUNCT}])`, 'g');
const RE_AFTER_ITALIC = new RegExp(`(?<!\\*)\\*([${CJK_PUNCT}])`, 'g');

function preprocessRegex(_text: string): string {
  // Passthrough — remark-parse v11 handles CJK punct + emphasis correctly.
  // Inserting spaces here breaks valid bold (e.g. 」** → 」 **).
  return _text;
}

// ---------------------------------------------------------------------------
// Strategy 2: AST (remark-parse)
// ---------------------------------------------------------------------------

type AstProcessor = ((text: string) => string) | null;
let astFn: AstProcessor = null;
let astLoadStarted = false;
let astLoadFailed = false;

function startAstLoad(): void {
  if (astLoadStarted) return;
  astLoadStarted = true;

  Promise.all([
    import('unified'),
    import('remark-parse'),
    import('remark-stringify'),
  ])
    .then(([unifiedMod, remarkParseMod, remarkStringifyMod]) => {
      const u = (unifiedMod as any).default ?? unifiedMod;
      const rp = (remarkParseMod as any).default ?? remarkParseMod;
      const rs = (remarkStringifyMod as any).default ?? remarkStringifyMod;
      const processor = u().use(rp).use(rs);

      astFn = (text: string): string => {
        if (PROTOCOL_BLOCK_RE.test(text)) return text;
        const tree = processor.parse(text);
        walkAndFix(tree);
        return String(processor.stringify(tree));
      };
    })
    .catch(() => {
      // ESM load failed — stay on regex fallback
      astLoadFailed = true;
    });
}

// mdast node types (duck-typed, no import needed)
interface MdastNode {
  type: string;
  children?: MdastNode[];
  value?: string;
}

/** Walk phrasing containers and insert spaces at CJK punct / delimiter boundaries. */
function walkAndFix(tree: MdastNode): void {
  const queue: MdastNode[] = [tree];
  while (queue.length) {
    const node = queue.shift()!;
    if (!node.children) continue;
    for (const child of node.children) queue.push(child);

    // Only fix phrasing containers (paragraph, heading, tableCell, etc.)
    if (
      node.type !== 'paragraph' &&
      node.type !== 'heading' &&
      node.type !== 'tableCell' &&
      node.type !== 'listItem'
    ) continue;

    const kids = node.children;
    for (let i = 0; i < kids.length - 1; i++) {
      const left = kids[i];
      const right = kids[i + 1];

      // text(ending CJK punct) → strong/emphasis
      if (
        left.type === 'text' && left.value &&
        (right.type === 'strong' || right.type === 'emphasis') &&
        left.value.length > 0
      ) {
        const last = left.value[left.value.length - 1];
        if (isCjkPunct(last)) {
          left.value += ' ';
        }
      }

      // strong/emphasis → text(starting CJK punct)
      if (
        (left.type === 'strong' || left.type === 'emphasis') &&
        right.type === 'text' && right.value &&
        right.value.length > 0
      ) {
        const first = right.value[0];
        if (isCjkPunct(first)) {
          right.value = ' ' + right.value;
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function preprocessMarkdown(text: string): string {
  if (MODE === 'ast') {
    if (!astLoadStarted) startAstLoad();
    if (astFn) return astFn(text);
    // Not yet loaded — regex fallback for this call
    return preprocessRegex(text);
  }
  return preprocessRegex(text);
}

export function getPreprocessMode(): PreprocessMode {
  return MODE;
}
