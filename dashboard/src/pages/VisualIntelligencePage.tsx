import React from "react";
import { ContainerScroll } from "@/components/ui/container-scroll-animation";
import { ImageStreamHero, type StreamImage } from "@/components/ui/image-stream-hero";

const STREAM_IMAGES: StreamImage[] = [
  {
    src: "https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=900&q=80",
    alt: "Modern operations room",
  },
  {
    src: "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=900&q=80",
    alt: "Technology workspace",
  },
  {
    src: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?auto=format&fit=crop&w=900&q=80",
    alt: "People working with technology",
  },
  {
    src: "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=900&q=80",
    alt: "Cybersecurity technology",
  },
  {
    src: "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=900&q=80",
    alt: "Electronic hardware close-up",
  },
];

export default function VisualIntelligencePage() {
  return (
    <div className="min-h-screen space-y-8 bg-[#02060a] text-white">
      <section className="overflow-hidden rounded-3xl border border-cyan-400/10 bg-[#08111a]">
        <ImageStreamHero images={STREAM_IMAGES} cards={9} speed={18} axis={54} className="h-[520px] w-full">
          <div className="relative z-10 flex h-full flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 font-mono text-[10px] tracking-[0.24em] text-cyan-300">
              GHOST TRAIL / VISUAL INTELLIGENCE
            </div>
            <h1 className="max-w-4xl text-4xl font-semibold tracking-tight text-white sm:text-6xl">
              See the environment as a continuous intelligence layer.
            </h1>
            <p className="mt-5 max-w-2xl text-sm leading-6 text-slate-400 sm:text-base">
              Image streams, spatial context and identity continuity are presented as one operational view without replacing the live surveillance pipeline.
            </p>
          </div>
        </ImageStreamHero>
      </section>

      <section className="rounded-3xl border border-white/10 bg-[#050a10] px-4 py-2 md:px-8">
        <ContainerScroll
          titleComponent={
            <div className="px-4">
              <p className="font-mono text-xs tracking-[0.25em] text-cyan-400">ROOM RECONSTRUCTION</p>
              <h2 className="mt-3 text-4xl font-semibold tracking-tight text-white md:text-6xl">
                Scroll through the <span className="text-cyan-300">environment model.</span>
              </h2>
              <p className="mx-auto mt-4 max-w-2xl text-sm text-slate-400">
                A reusable presentation layer for the room-scan output. The underlying scanner remains independent from surveillance capture.
              </p>
            </div>
          }
        >
          <div className="relative h-full overflow-hidden rounded-xl border border-cyan-400/15 bg-[#07131d]">
            <img
              src="https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1800&q=85"
              alt="Technology environment used as the room reconstruction presentation surface"
              className="h-full w-full object-cover opacity-45"
            />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(34,211,238,.18),transparent_55%)]" />
            <div className="absolute inset-0 bg-[linear-gradient(rgba(34,211,238,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,.08)_1px,transparent_1px)] bg-[size:36px_36px]" />
            <div className="absolute left-6 top-6 rounded-lg border border-cyan-300/20 bg-black/55 px-3 py-2 font-mono text-[10px] text-cyan-200 backdrop-blur">
              SCAN STATUS: PRESENTATION MODE
            </div>
            <div className="absolute bottom-6 left-6 right-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["FEATURES", "ORB / RANSAC"],
                ["OVERLAP", "VALIDATED"],
                ["IDENTITY", "MULTI-TEMPLATE"],
                ["CAMERA", "EXCLUSIVE SESSION"],
              ].map(([label, value]) => (
                <div key={label} className="rounded-lg border border-white/10 bg-black/55 p-3 backdrop-blur">
                  <div className="font-mono text-[9px] tracking-widest text-slate-500">{label}</div>
                  <div className="mt-1 text-xs font-medium text-white">{value}</div>
                </div>
              ))}
            </div>
          </div>
        </ContainerScroll>
      </section>
    </div>
  );
}
