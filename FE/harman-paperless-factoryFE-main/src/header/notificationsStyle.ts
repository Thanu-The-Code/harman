import styled from "styled-components";

export const NotificationsPageLayout = styled.div`
  min-height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 0 16px 16px;
  background: #f8fafc;
  color: #182338;
`;

export const NotificationsPageTitle = styled.div`
  min-height: 54px;
  display: flex;
  align-items: center;
  gap: 14px;

  h1 {
    margin: 0 0 2px;
    color: #172033;
    font-size: 18px;
    font-weight: 650;
  }

  p {
    margin: 0;
    color: #7b8798;
    font-size: 11px;
  }
`;

export const BackButton = styled.button`
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid #e0e6ed;
  border-radius: 5px;
  background: #ffffff;
  color: #344054;
  font-size: 26px;
  line-height: 1;
  cursor: pointer;

  &:hover {
    background: #f1f5f9;
  }
`;

export const NotificationsWorkspace = styled.div<{ $detailsOpen: boolean }>`
  min-height: 430px;
  flex: 1;
  display: grid;
  grid-template-columns: ${({ $detailsOpen }) =>
    $detailsOpen ? "minmax(0, 1.45fr) minmax(300px, 1fr)" : "minmax(0, 1fr)"};
  gap: 12px;

  @media (max-width: 760px) {
    grid-template-columns: 1fr;
  }
`;

export const NotificationsContent = styled.section`
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e0e6ed;
  border-radius: 6px;
  background: #ffffff;

  .notification-list {
    min-height: 0;
    flex: 1;
    overflow: auto;
  }

  .empty-notifications {
    min-height: 360px;
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 24px 16px;
    text-align: center;

    img {
      display: block;
      width: min(290px, 70vw);
      height: auto;
      margin-bottom: 20px;
    }

    h2 {
      margin: 0 0 10px;
      color: #182338;
      font-size: 20px;
      font-weight: 650;
    }

    p {
      margin: 0;
      color: #8994a5;
      font-size: 13px;
      line-height: 1.6;
    }

    @media (max-width: 600px) {
      min-height: 300px;

      h2 {
        font-size: 18px;
      }

      p {
        font-size: 12px;
      }

      br {
        display: none;
      }
    }
  }

  .notification-row {
    width: 100%;
    min-height: 65px;
    display: grid;
    grid-template-columns: 36px minmax(0, 1fr) auto 12px;
    align-items: center;
    gap: 10px;
    padding: 12px;
    border: 0;
    border-bottom: 1px solid #e5eaf0;
    background: #ffffff;
    color: inherit;
    text-align: left;
    cursor: pointer;

    &:hover,
    &.selected {
      background: #f7f9fb;
    }

    .notification-icon {
      width: 35px;
      height: 35px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      position: relative;
      background: #d2efff;
      color: #009cff;

      svg {
        width: 20px;
        height: 20px;
      }
    }

    &:nth-child(3n + 2) .notification-icon {
      background: #ffe1e1;
      color: #ff4f55;
    }

    &:nth-child(3n) .notification-icon {
      background: #fff0d8;
      color: #ff9900;
    }

    .unread-dot {
      position: absolute;
      top: 0px;
      right: -2px;
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #10b8ac;
      border: 1px solid white;
    }

    .notification-copy {
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 3px;

      strong {
        overflow: hidden;
        color: #1b2638;
        font-size: 14px;
        font-weight: 700;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      span {
        display: -webkit-box;
        overflow: hidden;
        color: #808A97;
        font-size: 12px;
        line-height: 1.35;
        -webkit-box-orient: vertical;
        -webkit-line-clamp: 2;
      }
    }

    time {
    color: #808A97;
      font-size: 12px;
      white-space: nowrap;
    }

    .chevron {
      color: #344054;
      font-size: 20px;
      line-height: 1;
    }
  }

  @media (max-width: 600px) {
    .notification-row {
      grid-template-columns: 36px minmax(0, 1fr) 12px;

      time {
        display: none;
      }
    }
  }
`;

export const NotificationsToolbar = styled.div`
  min-height: 46px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-bottom: 1px solid #e5eaf0;

  @media (max-width: 600px) {
    flex-wrap: wrap;
  }
`;

export const NotificationsSearch = styled.input`
  min-width: 90px;
  height: 28px;
  flex: 1;
  box-sizing: border-box;
  padding: 0 10px;
  border: 1px solid #dfe5ec;
  border-radius: 5px;
  outline: none;
  color: #344054;
  font: inherit;
  font-size: 10px;

  &:focus {
    border-color: #67bdf5;
    box-shadow: 0 0 0 2px rgba(0, 156, 255, 0.12);
  }

  &::placeholder {
    color: #a0a8b4;
  }
`;

export const FilterSelect = styled.select`
  height: 28px;
  min-width: 90px;
  padding: 0 8px;
  border: 1px solid #dfe5ec;
  border-radius: 5px;
  background: #ffffff;
  color: #344054;
  font: inherit;
  font-size: 10px;
`;

export const NotificationDetails = styled.section`
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #e0e6ed;
  border-radius: 6px;
  background: #ffffff;

  .empty-state {
    padding: 20px;
    color: #8994a5;
    font-size: 13px;
  }

  @media (max-width: 760px) {
    min-height: 360px;
  }
`;

export const DetailHeader = styled.div`
  min-height: 46px;
  box-sizing: border-box;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e5eaf0;

  h2 {
    margin: 0;
    color: #344054;
    font-size: 13px;
    font-weight: 600;
  }
`;

export const DetailCloseButton = styled.button`
  width: 27px;
  height: 27px;
  padding: 0;
  border: 1px solid #e5eaf0;
  border-radius: 5px;
  background: #ffffff;
  color: #8994a5;
  font-size: 18px;
  cursor: pointer;
`;

export const DetailsContent = styled.div`
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 14px;

  .selected-notification {
    display: flex;
    align-items: center;
    gap: 10px;

    .notification-icon {
      width: 35px;
      height: 35px;
      flex: 0 0 35px;
      display: grid;
      place-items: center;
      border-radius: 8px;
      background: #d2efff;
      color: #009cff;

      svg {
        width: 20px;
        height: 20px;
      }
    }

    strong {
      display: block;
      color: #1b2638;
      font-size: 12px;
      font-weight: 600;
    }

    time {
      display: block;
      margin-top: 3px;
      color: #8994a5;
      font-size: 10px;
    }
  }

  .description {
    margin: 16px 0 22px;
    padding: 12px;
    border: 1px solid #e5eaf0;
    border-radius: 7px;
    background: #f8fafc;
    color: #344054;
    font-size: 12px;
    line-height: 1.45;
  }

  dl {
    display: grid;
    grid-template-columns: minmax(90px, 0.75fr) minmax(0, 1.25fr);
    align-items: center;
    gap: 16px 10px;
    margin: 0;
  }

  dt {
    color: #8994a5;
    font-size: 11px;
  }
`;

export const TypeBadge = styled.span`
  display: inline-block;
  padding: 4px 10px;
  border: 1px solid #cde3ff;
  border-radius: 5px;
  background: #eef6ff;
  color: #3b82d0;
  font-size: 10px;
`;

export const DetailPerson = styled.span`
  display: flex;
  align-items: center;
  gap: 7px;

  .avatar {
    width: 25px;
    height: 25px;
    flex: 0 0 25px;
    display: grid;
    place-items: center;
    border-radius: 7px;
    background: #159c99;
    color: white;
    font-size: 11px;
  }

  strong,
  small {
    display: block;
    color: #344054;
    font-size: 10px;
  }

  small {
    margin-top: 2px;
    color: #8994a5;
  }
`;

export const DetailValue = styled.dd`
  margin: 0;
  color: #344054;
  font-size: 11px;
  line-height: 1.4;
`;

export const DetailActions = styled.div`
  min-height: 48px;
  box-sizing: border-box;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid #e5eaf0;

  button {
    min-width: 78px;
    height: 28px;
    padding: 0 9px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    border: 1px solid #dfe5ec;
    border-radius: 5px;
    background: #ffffff;
    color: #344054;
    font: inherit;
    font-size: 11px;
    cursor: pointer;

    &:disabled {
      color: #b8c0ca;
      cursor: default;
    }
  }
`;
