import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[var(--radius-md)] text-sm font-medium transition-all duration-[var(--duration-normal)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--aura-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--aura-bg-base)] disabled:pointer-events-none disabled:opacity-40 select-none",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--aura-accent)] text-white hover:bg-[var(--aura-accent-dim)] active:scale-[0.98] shadow-[var(--shadow-sm)]",
        secondary:
          "bg-[var(--aura-bg-elevated)] text-[var(--aura-text-primary)] border border-[var(--aura-border)] hover:bg-[var(--aura-bg-overlay)] hover:border-[var(--aura-border-strong)]",
        ghost:
          "text-[var(--aura-text-secondary)] hover:text-[var(--aura-text-primary)] hover:bg-[var(--aura-bg-hover)]",
        danger:
          "bg-[var(--aura-error-subtle)] text-[var(--aura-error)] border border-[rgba(239,68,68,0.2)] hover:bg-[var(--aura-error)] hover:text-white",
        success:
          "bg-[var(--aura-success-subtle)] text-[var(--aura-success)] border border-[rgba(34,197,94,0.2)] hover:bg-[var(--aura-success)] hover:text-white",
        link: "text-[var(--aura-accent)] underline-offset-4 hover:underline p-0 h-auto",
      },
      size: {
        sm: "h-7 px-3 text-xs",
        md: "h-9 px-4",
        lg: "h-11 px-6 text-base",
        icon: "h-9 w-9 p-0",
        "icon-sm": "h-7 w-7 p-0",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  loading?: boolean;
  isLoading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, loading, isLoading, children, disabled, ...props }, ref) => {
    const isSpinning = loading || isLoading;
    return (
      <button
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || isSpinning}
        {...props}
      >
        {isSpinning && (
          <svg
            className="animate-aura-spin h-4 w-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        )}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";
