/**
 * DIAGLOB brand emblem with an explicit image for each application theme.
 * Using CSS selectors on data-theme follows the manual theme toggle (not OS).
 */
type DiaglobBrandMarkProps = {
  width?: number;
  height?: number;
  className?: string;
};

export default function DiaglobBrandMark({
  width = 25,
  height = width,
  className = "",
}: DiaglobBrandMarkProps) {
  return (
    <span
      className={["diaglob-brand-mark", className].filter(Boolean).join(" ")}
      style={{ width, height }}
      aria-hidden="true"
    >
      <img
        className="diaglob-brand-mark-light"
        src="/brand/diaglob-mark.svg?v=coral-20261118"
        alt=""
        width={width}
        height={height}
        draggable={false}
      />
      <img
        className="diaglob-brand-mark-dark"
        src="/brand/diaglob-mark-dark.svg?v=coral-20261118"
        alt=""
        width={width}
        height={height}
        draggable={false}
      />
    </span>
  );
}
