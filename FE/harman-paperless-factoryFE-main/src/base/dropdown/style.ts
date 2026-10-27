import styled from "styled-components";

export const SelectWrapper = styled.div`
  position: relative;
  min-width: 220px;
  width: 220px;

  @media (max-width: 768px) {
    width: 100%;
    min-width: 100%;
  }
`;

export const SelectField = styled.select`
  width: 100%;
  height: 44px;
  padding: 0 42px 0 14px;
  border: 1px solid #d0d5dd;
  border-radius: 10px;
  background: #ffffff;
  color: #344054;
  font-size: 14px;
  font-weight: 500;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;

  &:focus {
    border-color: #98a2b3;
    box-shadow: 0 0 0 3px rgba(152, 162, 179, 0.14);
  }

  &:disabled {
    cursor: not-allowed;
    background: #f9fafb;
    color: #98a2b3;
  }
`;

export const SelectIcon = styled.span`
  position: absolute;
  top: 50%;
  right: 14px;
  transform: translateY(-50%);
  color: #667085;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
`;