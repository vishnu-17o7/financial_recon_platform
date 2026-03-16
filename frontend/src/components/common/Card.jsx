export default function Card({ className = "", children }) {
  const merged = className ? `card ${className}` : "card";
  return <section className={merged}>{children}</section>;
}
