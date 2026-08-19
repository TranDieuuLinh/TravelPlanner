type DestinationSourceLinkProps = {
  href?: string | null;
};

export function DestinationSourceLink({ href }: DestinationSourceLinkProps) {
  if (!href?.startsWith("http")) return null;

  return (
    <a
      aria-label="Xem nguồn"
      className="destinationSourceIcon"
      href={href}
      rel="noreferrer"
      target="_blank"
      title="Xem nguồn"
    >
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M14 5h5v5M19 5l-9 9" />
        <path d="M17 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5" />
      </svg>
    </a>
  );
}
