export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-6 py-16">
      <p className="text-micro uppercase text-faint">Flight compensation</p>
      <h1 className="text-display text-strong mt-3">Are you owed money?</h1>
      <p className="text-body text-muted mt-5 max-w-prose">
        The check form arrives in step 22. For now the design system is at{" "}
        <a className="text-brand-600 underline underline-offset-4" href="/styleguide">
          /styleguide
        </a>
        .
      </p>
    </main>
  );
}
