import ReferenceBubbleMap from './ReferenceBubbleMap';

export default function FlowGraph3D(props) {
  return <div className="relative isolate overflow-hidden rounded-2xl">
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-10 overflow-hidden rounded-2xl">
      <div className="absolute left-[42%] top-[44%] h-56 w-56 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-400/[0.035] blur-3xl animate-pulse" />
      <div className="absolute right-[16%] top-[24%] h-40 w-40 rounded-full bg-sky-400/[0.025] blur-3xl animate-pulse" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_58%_50%,rgba(56,189,248,0.035),transparent_34%,rgba(2,6,17,0.08)_76%)]" />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/20 to-transparent" />
    </div>
    <div className="relative z-0">
      <ReferenceBubbleMap {...props} />
    </div>
  </div>;
}
