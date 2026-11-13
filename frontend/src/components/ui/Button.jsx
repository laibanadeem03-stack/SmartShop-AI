import { Link } from 'react-router';

export function Button({ children, variant = 'primary', to, href, className = '', ...props }) {
  const classes = `button button-${variant} ${className}`;
  if (to) return <Link className={classes} to={to} {...props}>{children}</Link>;
  if (href) return <a className={classes} href={href} {...props}>{children}</a>;
  return <button className={classes} type="button" {...props}>{children}</button>;
}
