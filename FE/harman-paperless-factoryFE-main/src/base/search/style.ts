import styled from "styled-components";

export const SearchWrapper = styled.div`
  position: relative;
  flex: 0 1 314px;
  min-width: 220px;
  width: 100%;

  @media (max-width: 560px) {
    flex: 1 1 100%;
    min-width: 100%;
  }
`;

export const SearchIconHolder = styled.span`
  position: absolute;
  top: 50%;
  left: 13px;
  transform: translateY(-50%);
  color: #8b91a0;
  pointer-events: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;

  img,
  svg {
    width: 16px;
    height: 16px;
    display: block;
    object-fit: contain;
  }
`;

export const SearchField = styled.input<{ $withIcon?: boolean }>`
  width: 100%;
  height: 40px;
  padding: ${({ $withIcon }) => ($withIcon ? "0 12px 0 36px" : "0 12px")};
  border: 1px solid #dce3f1;
  border-radius: 9px;
  outline: none;
  background: #fff;
  color: #222838;
  font: inherit;
  font-size: 14px;
  box-sizing: border-box;

  &::placeholder {
    color: #9196a2;
  }

  &:focus {
    border-color: #4c43c6;
    box-shadow: 0 0 0 3px #4c43c61a;
  }

  &:disabled {
    background: #f7f8fb;
    color: #98a2b3;
    cursor: not-allowed;
  }

  &::-webkit-search-cancel-button {
    cursor: pointer;
  }
`;