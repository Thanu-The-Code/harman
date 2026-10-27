import styled from "styled-components";

export const HeaderContainer = styled.header`
  height: 60px;
  background-color: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  flex-shrink: 0;
`;

export const HeaderLeft = styled.div`
  display: flex;
  flex-direction: column;

  h1 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    color: #111827;
  }

  /* breadcrumb: "Template builder / Document create" */
  h1 .crumb {
    border: 0;
    padding: 0;
    background: none;
    font: inherit;
    font-weight: 400;
    color: #9ca3af;
    cursor: pointer;
  }
  h1 .crumb:hover {
    color: #14b8a6;
  }
  h1 .crumb-sep {
    font-weight: 400;
    color: #9ca3af;
  }

  p {
    margin: 4px 0 0 0;
    font-size: 13px;
    color: #6b7280;
  }
`;

export const HeaderRight = styled.div`
  display: flex;
  align-items: center;
  gap: 20px;
`;

export const NotificationControl = styled.div`
  display: flex;
`;

export const IconButton = styled.button`
  background: none;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: #6b7280;
  position: relative;
  transition: all 0.2s;

  &:hover {
    background: #f3f4f6;
    color: #111827;
  }

  .badge {
    position: absolute;
    top: -4px;
    right: -4px;
    background-color: #ef4444;
    color: white;
    font-size: 10px;
    font-weight: bold;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 2px solid white;
  }
`;

export const NotificationPanel = styled.div`
  position: fixed;
  z-index: 1000;
  top: 72px;
  right: 16px;
  width: min(750px, calc(100vw - 32px));
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  box-sizing: border-box;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.16);
  color: #111827;
  text-align: left;

  @media (max-width: 600px) {
    top: 68px;
    right: 8px;
    width: calc(100vw - 16px);
    max-height: calc(100vh - 76px);
  }
`;

export const NotificationPanelHeader = styled.div`
  min-height: 65px;
  padding: 0 20px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e2e8f0;

  h2 {
    margin: 0;
    color: #111827;
    font-size: 22px;
    line-height: 1.3;
    font-weight: 600;
  }

  button {
    padding: 0;
    border: 0;
    background: none;
    color: #00b7ad;
    font-size: 18px;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;

    &:hover {
      color: #008f87;
      text-decoration: underline;
    }
  }
`;

export const NotificationItem = styled.article`
  min-height: 90px;
  padding: 18px 20px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr) auto 20px;
  align-items: center;
  gap: 22px;
  border-bottom: 1px solid #e2e8f0;

  @media (max-width: 600px) {
    min-height: 112px;
    padding: 18px 14px;
    grid-template-columns: 48px minmax(0, 1fr) 16px;
    gap: 12px;
  }
`;

export const NotificationIcon = styled.div<{
  $tone: "blue" | "red" | "orange" | "green";
}>`
  width: 42px;
  height: 42px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  background: ${({ $tone }) =>
    $tone === "blue" ? "#d2efff" : $tone === "red" ? "#ffe1e1" : $tone === "green" ? "#dcfce7" : "#fff0d8"};
  color: ${({ $tone }) =>
    $tone === "blue" ? "#009cff" : $tone === "red" ? "#ff4f55" : $tone === "green" ? "#15803d" : "#ff9900"};

  svg {
    width: 20px;
    height: 20px;
  }

  .unread {
    position: absolute;
    width: 10px;
    height: 10px;
    top: 0px;
    right: -3px;
    border: 2px solid #ffffff;
    border-radius: 50%;
    background: #10b8ac;
    box-sizing: content-box;
  }

  @media (max-width: 600px) {
    width: 48px;
    height: 48px;

    svg {
      width: 25px;
      height: 25px;
    }
  }
`;

export const NotificationCopy = styled.div`
  min-width: 0;

  h3 {
    margin: 0 0 8px;
    color: #111827;
    font-size: 14px;
    line-height: 1.25;
    font-weight: 700;
  }

  p {
    margin: 0;
    color: #141b28;
    font-size: 12px;
    line-height: 1.35;
  }

  &[data-read="true"] p {
    color: #8994a5;
  }

  @media (max-width: 600px) {
    h3 {
      margin-bottom: 5px;
      font-size: 15px;
    }

    p {
      font-size: 13px;
    }
  }
`;

export const NotificationTime = styled.time`
  align-self: start;
  margin-top: 2px;
  color: #808A97;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 500;

  @media (max-width: 600px) {
    grid-column: 2;
    grid-row: 2;
    margin-top: -8px;
    font-size: 12px;
  }
`;

export const NotificationChevron = styled.span`
  color: #111827;
  font-size: 24px;
  line-height: 1;

  @media (max-width: 600px) {
    grid-column: 3;
    grid-row: 1 / span 2;
    font-size: 24px;
  }
`;

export const UserProfile = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
`;

export const Avatar = styled.div`
  width: 36px;
  height: 36px;
  background-color: #4f46e5;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
`;

export const UserInfo = styled.div`
  display: flex;
  flex-direction: column;

  .name {
    font-size: 14px;
    font-weight: 600;
    color: #111827;
  }

  .role {
    font-size: 12px;
    color: #6b7280;
  }
`;
