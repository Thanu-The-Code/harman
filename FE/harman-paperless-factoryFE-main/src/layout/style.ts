import styled from "styled-components";


export const MainLayoutWrapper = styled.div`
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: #F8F9FA;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
`;

export const RightColumn = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0; /* Prevents flex flex-child from overflowing */
`;

export const MainContent = styled.main`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  // padding: 24px;
`;



