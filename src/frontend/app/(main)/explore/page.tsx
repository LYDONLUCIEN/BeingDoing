'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

/** /explore 禁止访问，重定向到 /explore/intro（代码保留供参考） */
export default function ExploreChoicePage() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/explore/intro');
  }, [router]);

  return null;
}
