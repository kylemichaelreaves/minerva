export function SourceWithHighlight(props: {
  text: string;
  start: number | null;
  end: number | null;
}) {
  if (
    props.start === null ||
    props.end === null ||
    props.start < 0 ||
    props.end <= props.start ||
    props.end > props.text.length
  ) {
    return <span>{props.text}</span>;
  }
  return (
    <>
      <span>{props.text.slice(0, props.start)}</span>
      <mark class="review-hit">{props.text.slice(props.start, props.end)}</mark>
      <span>{props.text.slice(props.end)}</span>
    </>
  );
}
