import { SelectField, SelectIcon, SelectWrapper } from "./style";

export type CustomSelectOption = {
  label: string;
  value: string;
  disabled?: boolean;
};

type CustomSelectProps = {
  value: string;
  onChange: (value: string) => void;
  options: CustomSelectOption[];
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  name?: string;
  disabled?: boolean;
};

const CustomSelect = ({
  value,
  onChange,
  options,
  placeholder = "Select",
  ariaLabel,
  className,
  name,
  disabled = false,
}: CustomSelectProps) => {
  return (
    <SelectWrapper className={className}>
      <SelectField
        name={name}
        value={value}
        disabled={disabled}
        aria-label={ariaLabel || placeholder}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{placeholder}</option>

        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </SelectField>

      <SelectIcon aria-hidden="true">
        <svg
          width="16"
          height="16"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M5 7.5L10 12.5L15 7.5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </SelectIcon>
    </SelectWrapper>
  );
};

export default CustomSelect;