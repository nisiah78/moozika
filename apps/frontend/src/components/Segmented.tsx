"use client";

/**
 * Segmented control du design. La sélection passe par un radio natif masqué et
 * `:has(input:checked)` en CSS (cf. .moo-seg-opt) : le clavier, le groupement et
 * l'accessibilité viennent gratuitement, sans état à synchroniser.
 */
export function Segmented<T extends string>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T;
  options: { value: T; label: string; disabled?: boolean; title?: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="moo-seg">
      {options.map((o) => (
        <label key={o.value} className="moo-seg-opt" title={o.title}>
          <input
            type="radio"
            name={name}
            checked={value === o.value}
            disabled={o.disabled}
            onChange={() => onChange(o.value)}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}
