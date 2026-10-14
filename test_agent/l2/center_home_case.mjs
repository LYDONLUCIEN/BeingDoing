/** 首页阶段卡：验证实际排布、完整内容和点击，不以元素存在代替可访问。 */
export async function testHomeCards(page, check) {
  const cards = page.locator('.ol-phase-card');
  await cards.first().focus();
  const layout = await page.locator('.ol-phase-cards').evaluate(container => {
    const box = element => {
      const rect = element.getBoundingClientRect();
      return { x: rect.x, y: rect.y, right: rect.right, bottom: rect.bottom, width: rect.width };
    };
    return {
      width: innerWidth,
      narrow: matchMedia('(max-width: 720px)').matches,
      medium: matchMedia('(max-width: 1050px)').matches,
      cue: box(document.querySelector('.ol-scroll-cue')),
      scene: box(document.querySelector('.ol-home-scene')),
      overflow: container.scrollWidth > container.clientWidth + 1,
      cards: [...container.querySelectorAll('.ol-phase-card')].map(card => ({
        ...box(card),
        // 选中态沿用轻微上浮/缩放；用流内位置判断排布，实际边界仍检查内容可见。
        flow: { x: card.offsetLeft, y: card.offsetTop, width: card.offsetWidth, height: card.offsetHeight },
        icon: box(card.querySelector('.ol-phase-symbol')),
        title: box(card.querySelector('strong')),
        content: [...card.querySelectorAll('.ol-phase-no, strong, small')].map(element => ({
          ...box(element),
          complete: element.scrollWidth <= element.clientWidth + 1 && element.scrollHeight <= element.clientHeight + 1,
        })),
      })),
    };
  });
  check(layout.cards.length === 5, '保留五个探索阶段');
  check(!layout.overflow, `${layout.width}px: 阶段卡无需横向滑动`);
  for (const [index, card] of layout.cards.entries()) {
    check(card.x >= 0 && card.right <= layout.width + 1, `第 ${index + 1} 张卡完整位于页面宽度内`);
    check(card.content.every(text => text.complete && text.x >= card.x && text.right <= card.right + 1 && text.bottom <= card.bottom + 1), `第 ${index + 1} 张卡的标题和说明未裁切`);
    if (layout.narrow) {
      check(Math.abs(card.flow.x - layout.cards[0].flow.x) < 1 && Math.abs(card.flow.width - layout.cards[0].flow.width) < 1, '窄屏五张卡对齐且等宽');
      check(index === 0 || card.flow.y >= layout.cards[index - 1].flow.y + layout.cards[index - 1].flow.height + 8, '窄屏按阶段顺序纵向排列且不重叠');
      check(card.icon.right <= card.title.x - 8, '窄屏保留左侧图标、右侧文案的紧凑卡片');
    }
  }
  if (layout.narrow) {
    check(layout.cue.y >= layout.cards.at(-1).bottom + 8, '向下探索提示位于全部阶段卡之后，不遮住说明文字');
    check(layout.scene.bottom >= layout.cards.at(-1).bottom, '首屏随纵向内容自然增高，不裁掉后续卡片');
  }
  if (!layout.medium) {
    check(layout.cards.every(card => Math.abs(card.flow.y - layout.cards[0].flow.y) < 1), '普通桌面仍为五张卡并排');
  } else if (!layout.narrow) {
    check(layout.cards.slice(0, 3).every(card => Math.abs(card.flow.y - layout.cards[0].flow.y) < 1)
      && layout.cards[3].flow.y > layout.cards[0].flow.y + layout.cards[0].flow.height && Math.abs(layout.cards[3].flow.y - layout.cards[4].flow.y) < 1, '中等宽度保持原有三加二排布');
  }
  for (let index = 0; index < 5; index++) {
    await cards.nth(index).click();
    check(await cards.nth(index).getAttribute('aria-checked') === 'true', `第 ${index + 1} 张阶段卡可正常选择`);
  }
  if (layout.narrow) {
    check(await page.locator('.ol-home-scene').evaluate(scene => scene.scrollTop === 0 && scene.scrollLeft === 0), '仅靠正常页面滚动即可浏览五张卡，不依赖首屏内部隐藏滚动');
  }
}
