import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, hint, leftIcon, id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="text-xs font-medium text-[var(--aura-text-secondary)]"
          >
            {label}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--aura-text-muted)]">
              {leftIcon}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "w-full h-9 rounded-[var(--radius-md)] border bg-[var(--aura-bg-elevated)] text-sm text-[var(--aura-text-primary)] placeholder:text-[var(--aura-text-placeholder)] transition-all duration-[var(--duration-fast)]",
              "focus:outline-none focus:ring-2 focus:ring-[var(--aura-accent)] focus:border-transparent",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              leftIcon ? "pl-9 pr-3" : "px-3",
              error
                ? "border-[var(--aura-error)] focus:ring-[var(--aura-error)]"
                : "border-[var(--aura-border)] hover:border-[var(--aura-border-strong)]",
              className
            )}
            aria-invalid={!!error}
            aria-describedby={
              error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined
            }
            {...props}
          />
        </div>
        {error && (
          <p id={`${inputId}-error`} role="alert" className="text-xs text-[var(--aura-error)]">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={`${inputId}-hint`} className="text-xs text-[var(--aura-text-muted)]">
            {hint}
          </p>
        )}
      </div>
    );
  }
);
Input.displayName = "Input";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");
    return (
      <div className="flex flex-col gap-1.5 w-full">
        {label && (
          <label htmlFor={inputId} className="text-xs font-medium text-[var(--aura-text-secondary)]">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={inputId}
          className={cn(
            "w-full rounded-[var(--radius-md)] border bg-[var(--aura-bg-elevated)] px-3 py-2.5 text-sm text-[var(--aura-text-primary)] placeholder:text-[var(--aura-text-placeholder)] resize-none transition-all duration-[var(--duration-fast)]",
            "focus:outline-none focus:ring-2 focus:ring-[var(--aura-accent)] focus:border-transparent",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            error
              ? "border-[var(--aura-error)]"
              : "border-[var(--aura-border)] hover:border-[var(--aura-border-strong)]",
            className
          )}
          {...props}
        />
        {error && <p role="alert" className="text-xs text-[var(--aura-error)]">{error}</p>}
      </div>
    );
  }
);
Textarea.displayName = "Textarea";
