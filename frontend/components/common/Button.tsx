import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  fullWidth?: boolean;
  variant?: 'primary' | 'secondary' | 'quiet';
};

export function Button({
  children,
  className = '',
  fullWidth = false,
  type = 'button',
  variant = 'primary',
  ...props
}: ButtonProps) {
  return (
    <button
      className={`button button-${variant}${fullWidth ? ' is-full' : ''} ${className}`.trim()}
      type={type}
      {...props}
    >
      {children}
    </button>
  );
}
