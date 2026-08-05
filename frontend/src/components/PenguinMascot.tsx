import Image from "next/image";

type PenguinMascotVariant =
  | "chat"
  | "chatSpeaking"
  | "curious"
  | "hi"
  | "intakePeek"
  | "logo"
  | "plan"
  | "search";

const mascotSources: Record<PenguinMascotVariant, string> = {
  chat: "/images/penguin-travel-chat.png",
  chatSpeaking: "/images/penguin-travel-chat-speaking.png",
  curious: "/images/penguin-curious.png",
  hi: "/images/penguin-hi.png",
  intakePeek: "/images/penguin-intake-peek.png",
  logo: "/images/penguin-logo.png",
  plan: "/images/penguin-plan.png",
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
