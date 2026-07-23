import { cn } from "@/lib/utils";

interface CheckboxProps extends Omit<React.ComponentProps<"input">, "type"> {
  label?: string;
  hint?: string;
}

export function Checkbox({ className, label, hint, ...props }: CheckboxProps) {
  return (
    <label className="flex items-start gap-3">
      <input
        type="checkbox"
        className={cn(
          "mt-1 h-4 w-4 rounded border-zinc-300 accent-primary focus:ring-primary/30",
          className,
        )}
        {...props}
      />
      {(label || hint) && (
        <span className="space-y-0.5">
          {label && <span className="block text-sm font-medium text-zinc-700">{label}</span>}
          {hint && <span className="block text-xs text-zinc-500">{hint}</span>}
        </span>
      )}
    </label>
  );
}
