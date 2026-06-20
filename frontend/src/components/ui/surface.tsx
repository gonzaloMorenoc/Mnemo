interface SurfaceProps {
  title: string;
  description: string;
}

export function Surface({ title, description }: SurfaceProps) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-4">
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  );
}
