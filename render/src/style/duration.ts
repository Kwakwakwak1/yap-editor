import type {ResolvedStyle} from "./types";

/**
 * Seconds the endcard adds to the reel.
 *
 * Shared rather than inlined because THREE things have to agree: Root's
 * calculateMetadata (which decides how many frames are rendered), the Endcard
 * layer (which decides when to appear), and verify_reel's expected-duration
 * check in Python. Two of the three agreeing is a reel that fails verification
 * for a legitimate reason, which is the failure mode that teaches people to
 * ignore the checker.
 *
 * A block with no asset contributes nothing: resolve_style switches the whole
 * block off when the brand has no endcard, and a `durationSeconds` left behind
 * on its own would hold a black frame at the end of every reel.
 */
export function endcardSeconds(style: ResolvedStyle | undefined): number {
  const endcard = style?.furniture?.endcard;
  if (!endcard || !endcard.asset) return 0;
  const seconds = Number(endcard.durationSeconds ?? 0);
  return Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
}

/** The whole reel: the assembled cut, plus whatever furniture extends it. */
export function reelDurationSeconds(
  cutSeconds: number,
  style: ResolvedStyle | undefined,
): number {
  return cutSeconds + endcardSeconds(style);
}
