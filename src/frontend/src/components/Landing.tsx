'use client';

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";

export default function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const introRef = useRef<HTMLDivElement>(null);
  const wipeRef = useRef<HTMLDivElement>(null);
  const [shouldShow, setShouldShow] = useState(false);

  useEffect(() => {
    if (
      sessionStorage.getItem("introPlayed") ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) return;
    sessionStorage.setItem("introPlayed", "true");
    setShouldShow(true);
  }, []);

  useEffect(() => {
    if (!shouldShow || !introRef.current || !wipeRef.current) return;

    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ onComplete: () => setShouldShow(false) });

      tl.fromTo(
        "[data-intro-word]",
        { yPercent: 110 },
        {
          yPercent: 0,
          duration: 0.9,
          stagger: 0.14,
          ease: "power4.out",
        }
      )
        .fromTo(wipeRef.current, {
          yPercent: 100,
        }, {
          yPercent: -100,
          duration: 1.1,
          ease: "power4.inOut",
        })
        .to(introRef.current, {
          yPercent: -100,
          duration: 0.8,
          ease: "power4.inOut",
        }, "-=0.55");
    }, containerRef);

    return () => ctx.revert();
  }, [shouldShow]);

  if (!shouldShow) return null;

  return (
    <div ref={containerRef} aria-hidden="true" className="fixed inset-0 z-[100] overflow-hidden">
      <div ref={introRef} className="absolute inset-0 grid place-items-center overflow-hidden bg-[#071c16] text-[#f4f5eb]">
        <div className="absolute inset-x-6 top-6 flex items-center justify-between border-y border-white/10 py-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-white/55 sm:inset-x-10 sm:top-10">
          <span>KoroFarm</span>
          <span>Supply assurance</span>
        </div>
        <div className="text-center">
          <p className="mb-5 text-[10px] font-semibold uppercase tracking-[0.2em] text-[#43c982] sm:text-xs">
            Caribbean food systems
          </p>
          <div className="font-semibold leading-[0.98]">
            {["Guarantee", "Your", "Supply"].map((word) => (
              <h1 key={word} className="overflow-hidden text-[52px] sm:text-[72px] lg:text-[104px]">
                <span data-intro-word className="block">{word}</span>
              </h1>
            ))}
          </div>
        </div>
        <div className="absolute inset-x-6 bottom-6 flex items-center justify-between border-t border-white/10 pt-3 text-[10px] uppercase tracking-[0.16em] text-white/45 sm:inset-x-10 sm:bottom-10">
          <span>Planning · monitoring · recovery</span>
          <span>Jamaica</span>
        </div>
      </div>
      <div ref={wipeRef} className="absolute inset-0 z-10 bg-[#43c982]" />
    </div>
  );
}