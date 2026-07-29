import Image from "next/image";

type PenguinMascotVariant = "chat" | "logo" | "search";

const mascotSources: Record<PenguinMascotVariant, string> = {
  chat: "/images/penguin-chat.png",
  logo: "/images/penguin-logo.png",
  search: "/images/penguin-search.png",
};

type PenguinMascotProps = {
  className?: string;
  priority?: boolean;
  size: number;
  variant: PenguinMascotVariant;
};

export function PenguinMascot({
  className = "",
  priority = false,
  size,
  variant,
}: PenguinMascotProps) {
  return (
    <Image
      alt=""
      aria-hidden="true"
      className={`penguinMascot ${className}`.trim()}
      height={size}
      priority={priority}
      src={mascotSources[variant]}
      width={size}
    />
  );
}
