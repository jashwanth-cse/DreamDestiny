import React from "react";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "whatsapp" | "outline";
  size?: "sm" | "md" | "lg";
  href?: string;
  external?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = "primary",
      size = "md",
      href,
      external = false,
      icon,
      children,
      className = "",
      disabled,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      "inline-flex items-center justify-center font-semibold rounded-full transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed text-center focus-visible:outline-2 focus-visible:outline-offset-2";

    const variantStyles = {
      primary:
        "bg-[#0D0F10] text-white hover:bg-[#1A1C1D] hover:shadow-[0_8px_24px_rgba(13,15,16,0.15)] active:scale-[0.99] focus-visible:outline-[#0D0F10]",
      secondary:
        "bg-white text-[#0D0F10] border border-[rgba(13,15,16,0.12)] hover:bg-[#F2F6F6] hover:border-[rgba(13,15,16,0.2)] active:scale-[0.99] focus-visible:outline-[#0D0F10]",
      whatsapp:
        "bg-[#79B66A] text-white hover:bg-[#68A25A] shadow-[0_4px_14px_rgba(121,182,106,0.3)] hover:shadow-[0_6px_20px_rgba(121,182,106,0.4)] active:scale-[0.99] focus-visible:outline-[#79B66A]",
      outline:
        "bg-transparent text-[#0B2345] border border-[#0B2345]/20 hover:bg-[#0B2345]/5 focus-visible:outline-[#0B2345]",
    };

    const sizeStyles = {
      sm: "text-xs px-4 py-2 gap-1.5",
      md: "text-sm px-6 py-3 gap-2",
      lg: "text-base px-8 py-4 gap-2.5",
    };

    const combinedClasses = `${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`;

    if (href) {
      return (
        <a
          href={href}
          target={external ? "_blank" : undefined}
          rel={external ? "noopener noreferrer" : undefined}
          className={combinedClasses}
          aria-disabled={disabled}
        >
          {icon && <span className="shrink-0">{icon}</span>}
          <span>{children}</span>
        </a>
      );
    }

    return (
      <button
        ref={ref}
        disabled={disabled}
        className={combinedClasses}
        {...props}
      >
        {icon && <span className="shrink-0">{icon}</span>}
        <span>{children}</span>
      </button>
    );
  }
);

Button.displayName = "Button";
