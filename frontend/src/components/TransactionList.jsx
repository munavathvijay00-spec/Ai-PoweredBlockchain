import CleanReviewQueue from './CleanReviewQueue';

/**
 * Compatibility wrapper for the existing live-monitor page.
 * The previous implementation placed every review action, risk explanation and
 * evidence export directly inside each queue row. That made the queue visually
 * noisy and difficult to scan. CleanReviewQueue keeps the clustered backend
 * model while moving those secondary actions into a focused review drawer.
 */
export default function TransactionList(props) {
  return <CleanReviewQueue {...props} />;
}
