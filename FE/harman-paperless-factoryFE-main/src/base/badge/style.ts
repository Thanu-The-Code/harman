import styled, { css } from "styled-components";

const getStatusStyles = (status: string) => {
  switch (status) {
    case "pending":
      return css`
        color: #ff6b00;
        background: #fff4e8;
        border: 1px solid #ffd39a;
      `;

    case "approved":
      return css`
        color: #119657;
        background: #ecfff3;
        border: 1px solid #c8efd8;
      `;

    case "rejected":
      return css`
        color: #d92d20;
        background: #fff1f0;
        border: 1px solid #f7c7c3;
      `;

    case "draft":
      return css`
        color: #667085;
        background: #f2f4f7;
        border: 1px solid #d0d5dd;
      `;

    case "active":
      return css`
        color: #027a48;
        background: #ecfdf3;
        border: 1px solid #abefc6;
      `;

    case "inactive":
      return css`
        color: #667085;
        background: #f2f4f7;
        border: 1px solid #d0d5dd;
      `;

    case "verification":
      return css`
        color: #b54708;
        background: #fffaeb;
        border: 1px solid #fedf89;
      `;

    case "completed":
      return css`
        color: #155eef;
        background: #eff4ff;
        border: 1px solid #b2ccff;
      `;

    default:
      return css`
        color: #344054;
        background: #f8fafc;
        border: 1px solid #dce3f1;
      `;
  }
};

export const BadgeWrapper = styled.div`
  position: relative;
  display: inline-flex;
  align-items: center;

  &:hover .status-tooltip {
    opacity: 1;
    visibility: visible;
    transform: translate(-50%, -6px);
  }
`;

export const BadgeText = styled.span<{ $status: string }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  font-family: "Satoshi", sans-serif;
  ${({ $status }) => getStatusStyles($status)};
`;

export const BadgeTooltip = styled.div`
  position: absolute;
  left: 50%;
  bottom: calc(100% + 10px);
  transform: translate(-50%, 0);
  background: #1d2939;
  color: #ffffff;
  font-size: 12px;
  line-height: 1.4;
  font-weight: 500;
  padding: 8px 10px;
  border-radius: 8px;
  white-space: nowrap;
  box-shadow: 0 8px 24px rgba(16, 24, 40, 0.18);
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
  z-index: 20;
  pointer-events: none;
  font-family: "Satoshi", sans-serif;

  &.status-tooltip {
  }

  &::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border-width: 5px;
    border-style: solid;
    border-color: #1d2939 transparent transparent transparent;
  }
`;