export default function Toast({ message, kind }) {
  const visible = Boolean(message);
  const variantClass = kind === "error" ? "toast error" : "toast";
  return <div className={visible ? `${variantClass} show` : variantClass}>{message}</div>;
}
