import styled from "styled-components";

export const SettingsPageLayout = styled.div`
  min-height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 10px 16px;
  background: #f8fafc;
  color: #182338;
`;

export const SettingsPageTitle = styled.div`
  min-height: 54px;
  display: flex;
  align-items: center;
  gap: 10px;

  h1 {
    margin: 0 0 2px;
    color: #172033;
    font-size: 20px;
    font-weight: 700;
  }

  p {
    margin: 0;
    color: #7b8798;
    font-size: 14px;
  }
`;

export const BackButton = styled.button`
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid #e0e6ed;
  border-radius: 5px;
  background: #ffffff;
  color: #344054;
  cursor: pointer;

  &:hover {
    background: #f1f5f9;
  }
`;

export const SettingsCard = styled.section`
  overflow: hidden;
  border: 1px solid #e0e6ed;
  border-radius: 5px;
  background: #ffffff;

  .card-header {
    min-height: 65px;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 7px 12px;
    border-bottom: 1px solid #e5eaf0;

    h2 {
      margin: 0 0 2px;
      color: #263246;
      font-size: 16px;
      font-weight: 600;
    }

    p {
      margin: 0;
      color: #7b8798;
      font-size: 12px;
    }
  }

  .change-password {
    padding: 8px 15px;
    border: 1px solid #c8f1ee;
    border-radius: 4px;
    background: #ecfbfa;
    color: #00aaa2;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    font-weight: 600;

    &:hover {
      background: #d9f7f4;
    }
  }

  .card-footer {
    min-height: 39px;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    padding: 6px 10px;
    border-top: 1px solid #e5eaf0;

    [role="status"] {
      color: #168f89;
      font-size: 10px;
    }
  }

  .save-button {
    padding: 8px 15px;
    border: 0;
    border-radius: 4px;
    background: #10b8ac;
    color: #ffffff;
    font: inherit;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;

    &:hover {
      background: #079b92;
    }
  }
`;

export const ProfileSection = styled.div`
  min-height: 174px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: minmax(190px, 28%) minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  padding: 12px;

  .profile-summary {
    display: flex;
    align-items: center;
    gap: 12px;
    padding-top: 1px;
  }

  .avatar {
    width: 85px;
    height: 85px;
    flex: 0 0 85px;
    position: relative;
    display: grid;
    place-items: center;
    border-radius: 14px;
    background: #10b8ac;
    color: #ffffff;
    font-size: 23px;
    font-weight: 700;

    span {
      position: absolute;
      right: -1px;
      bottom: -1px;
      width: 20px;
      height: 20px;
      display: grid;
      place-items: center;
      border: 1px solid #e5eaf0;
      border-radius: 4px;
      background: white;
      color: #64748b;
      font-size: 12px;
    }
  }

  .identity {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;

    strong {
      color: #263246;
      font-size: 12px;
    }

    > span {
      color: #7b8798;
      font-size: 10px;
    }

    .status {
      width: fit-content;
      margin-top: 3px;
      padding: 6px 16px;
      border-radius: 6px;
      background: #EAF9F8;
      color: #0EBBB1;
      font-size: 12px;
      font-weight: 600;
      border: 1px solide #CCF0EE;
    }
  }

  @media (max-width: 700px) {
    grid-template-columns: 1fr;
    gap: 14px;
  }
`;

export const ProfileFields = styled.div`
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;

  label {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;

    > span {
      color: #526073;
      font-size: 12px;
    }
  }

  input,
  select {
    width: 100%;
    height: 34px;
    box-sizing: border-box;
    padding: 0 7px;
    border: 1px solid #e0e6ed;
    border-radius: 6px;
    outline-color: #10b8ac;
    background: #f8fafc;
    color: #758195;
    font: inherit;
    font-size: 12px;
  }

  @media (max-width: 520px) {
    grid-template-columns: 1fr;
  }
`;

export const NotificationSetting = styled.div`
  min-height: 43px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 28px;
  align-items: center;
  gap: 32px;
  padding: 10px 12px;
  border-bottom: 1px solid #e5eaf0;

  &:last-child {
    border-bottom: 0;
  }

  .setting-icon {
    width: 40px;
    height: 40px;
    display: grid;
    place-items: center;
    border: 1px solid #DFE3EA;
    border-radius: 5px;
    color: #505d70;
  }

  .setting-copy {
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong {
      color: #344054;
      font-size: 14px;
      font-weight: 600;
    }

    small {
      overflow: hidden;
      color: #778397;
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
`;


