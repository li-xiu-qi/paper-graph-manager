import { useEffect } from "react";

export function useMobile() {
  useEffect(() => {
    const handleResize = () => {
      document.documentElement.classList.toggle("mobile", window.innerWidth < 768);
    };
    handleResize();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);
}
