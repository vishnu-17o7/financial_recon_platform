export default function Card({ as: Element = "section", className = "", children, ...rest }) {
  const merged = className ? `card ${className}` : "card";
  return <Element className={merged} {...rest}>{children}</Element>;
}
