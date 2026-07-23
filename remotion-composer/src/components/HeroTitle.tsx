import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface HeroTitleProps {
  title: string;
  subtitle?: string;
  /** Frames the title is on screen; the stagger is fit inside it. */
  windowFrames?: number;
}

export const HeroTitle: React.FC<HeroTitleProps> = ({
  title,
  subtitle,
  windowFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const words = title.split(/\s+/).filter(Boolean);
  const titleChars = title.split("");

  // Character index of the first letter of word `wi` (spaces excluded).
  const charIndexAt = (wi: number) =>
    words.slice(0, wi).reduce((n, w) => n + w.length, 0);

  // Long headlines used to overflow at a fixed 72px. Step the size down so
  // the whole title fits the frame instead of spilling out of it.
  const fontSize =
    titleChars.length > 70 ? 44
    : titleChars.length > 50 ? 52
    : titleChars.length > 34 ? 62
    : 72;

  // The stagger must FINISH while the card is still on screen. At a fixed
  // 1.2 frames/char a 60-character headline took 2.4s — longer than the 2s
  // the card exists — so it was cut off mid-animation. Fit the whole
  // stagger into the first ~55% of the window instead.
  const availableFrames = windowFrames ?? durationInFrames;
  const charDelay = Math.min(
    1.2,
    Math.max(0.15, (availableFrames * 0.55) / Math.max(1, titleChars.length))
  );

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        background:
          "radial-gradient(ellipse at center, rgba(15,23,42,0.35) 0%, rgba(15,23,42,0.55) 100%)",
      }}
    >
      <div style={{ textAlign: "center", maxWidth: "85%" }}>
        {/* Main title: characters animate individually but WRAP BY WORD.
            Flex-wrapping bare characters split words mid-word ("Day" →
            "D" + "ay" on the next line), so each word is its own nowrap
            flex item and the characters live inside it. */}
        <div
          style={{
            fontSize,
            fontWeight: 800,
            fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
            lineHeight: 1.2,
            display: "flex",
            justifyContent: "center",
            flexWrap: "wrap",
            columnGap: "0.28em",
            rowGap: 0,
          }}
        >
          {words.map((word, wi) => (
            <span
              key={wi}
              style={{ display: "inline-block", whiteSpace: "nowrap" }}
            >
              {word.split("").map((char, ci) => {
                const charSpring = spring({
                  frame: frame - (charIndexAt(wi) + ci) * charDelay,
                  fps,
                  config: { damping: 12, stiffness: 150 },
                });
                return (
                  <span
                    key={ci}
                    style={{
                      display: "inline-block",
                      opacity: charSpring,
                      transform: `translateY(${interpolate(
                        charSpring,
                        [0, 1],
                        [30, 0]
                      )}px)`,
                      color: wi === 0 ? "#22D3EE" : "#F8FAFC",
                    }}
                  >
                    {char}
                  </span>
                );
              })}
            </span>
          ))}
        </div>

        {/* Subtitle */}
        {subtitle && (
          <div
            style={{
              marginTop: 20,
              opacity: spring({
                frame: frame - titleChars.length * charDelay - 3,
                fps,
                config: { damping: 20 },
              }),
              fontSize: 28,
              fontWeight: 400,
              color: "#A78BFA",
              fontFamily: "Space Grotesk, Inter, system-ui, sans-serif",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {subtitle}
          </div>
        )}

        {/* Animated underline */}
        <div
          style={{
            margin: "24px auto 0",
            height: 3,
            backgroundColor: "#22D3EE",
            borderRadius: 2,
            width: interpolate(
              spring({
                frame: frame - 15,
                fps,
                config: { damping: 15, stiffness: 60 },
              }),
              [0, 1],
              [0, 400]
            ),
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
