import { useEffect, useRef } from "react";
import gsap from "gsap";

export default function Landing() {
  const containerRef = useRef<HTMLDivElement>(null);
  const hasPlayed = sessionStorage.getItem("introPlayed");
    if (hasPlayed) sessionStorage.setItem("introPlayed", "true");
   

  useEffect(() => {
    // GSAP context keeps animations scoped + auto-cleaned
    const ctx = gsap.context(() => {
      const tl = gsap.timeline();

      // Text reveal
      tl.fromTo(
        ".text",
        { y: "100%" },
        {
          y: "0%",
          duration: 1,
          stagger: 0.25,
          ease: "power4.out",
        }
      )
        // Slider wipe
        .to(".slider", {
          y: "-100%",
          duration: 1.5,
          delay: 0.5,
          ease: "power4.inOut",
        })
        // intro screen exits
        .to(
          ".intro",
          {
            y: "-100%",
            duration: 0.8,
            ease: "power4.inOut",
          },
          "-=1"
        )
        // unlock app interaction
        .set([".intro", ".slider"], {
          pointerEvents: "none",
        });
    }, containerRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={containerRef}>

      {/* Intro Overlay */}
      <div className="intro">
        <div className="intro-text">
          <h1 className="hide">
            <span className="text">Optimize</span>
          </h1>

          <h1 className="hide">
            <span className="text">Your</span>
          </h1>

          <h1 className="hide">
            <span className="text">Campus</span>
          </h1>
        </div>
      </div>

      {/* Slider Wipe */}
      <div className="slider"></div>
    </div>
  );
}