import { useRef, useState } from "react";
import { DateField, DateIconButton, DateWrapper } from "./style";

type DatePickerProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  name?: string;
  disabled?: boolean;
  min?: string;
  max?: string;
};

const DatePicker = ({
  value,
  onChange,
  placeholder = "Select Date",
  ariaLabel,
  className,
  name,
  disabled = false,
  min,
  max,
}: DatePickerProps) => {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [isFocused, setIsFocused] = useState(false);

  const inputType = isFocused || value ? "date" : "text";

  const openPicker = () => {
    if (disabled) return;

    inputRef.current?.focus();

    requestAnimationFrame(() => {
      if (inputRef.current?.showPicker) {
        inputRef.current.showPicker();
      }
    });
  };

  return (
    <DateWrapper className={className}>
      <DateField
        ref={inputRef}
        type={inputType}
        name={name}
        value={value}
        min={min}
        max={max}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={ariaLabel || placeholder}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        onChange={(event) => onChange(event.target.value)}
        onClick={openPicker}
      />

      <DateIconButton
        type="button"
        onClick={openPicker}
        disabled={disabled}
        aria-label="Open date picker"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            d="M8 2V5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
          <path
            d="M16 2V5"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
          <rect
            x="3"
            y="4"
            width="18"
            height="17"
            rx="3"
            stroke="currentColor"
            strokeWidth="1.8"
          />
          <path
            d="M3 9H21"
            stroke="currentColor"
            strokeWidth="1.8"
          />
        </svg>
      </DateIconButton>
    </DateWrapper>
  );
};

export default DatePicker;