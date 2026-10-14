'use client';

import { useEffect, useState } from 'react';

/** 与手机布局断点共用，不根据浏览器身份猜测设备。 */
export function useMobileLayout() {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const query = window.matchMedia('(max-width: 767px)');
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);
  return mobile;
}
