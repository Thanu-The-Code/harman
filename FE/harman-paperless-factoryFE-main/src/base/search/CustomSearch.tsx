import { SearchField, SearchIconHolder, SearchWrapper } from "./style";
import { ConstantLogo } from "../../assets";

type CustomSearchBoxProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  ariaLabel?: string;
  className?: string;
  name?: string;
  disabled?: boolean;
  type?: "search" | "text";
  hideIcon?: boolean;
};

const CustomSearchBox = ({
  value,
  onChange,
  placeholder = "Search",
  ariaLabel,
  className,
  name,
  disabled = false,
  type = "search",
  hideIcon = false,
}: CustomSearchBoxProps) => {
  const { search_logo } = ConstantLogo;

  return (
    <SearchWrapper className={className}>
      {!hideIcon && (
        <SearchIconHolder>
          <img src={search_logo} alt="search" />
        </SearchIconHolder>
      )}

      <SearchField
        $withIcon={!hideIcon}
        type={type}
        name={name}
        value={value}
        disabled={disabled}
        aria-label={ariaLabel || placeholder}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    </SearchWrapper>
  );
};

export default CustomSearchBox;