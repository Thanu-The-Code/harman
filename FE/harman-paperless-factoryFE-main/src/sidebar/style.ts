import styled from "styled-components";
import { NavLink } from "react-router-dom";

const EXPANDED_WIDTH = "240px";
const COLLAPSED_WIDTH = "60px";

export const SidebarContainer = styled.aside<{ $collapsed: boolean }>`
  position: relative; /* anchor for the toggle button */
  z-index: 10;
  width: ${({ $collapsed }) => ($collapsed ? COLLAPSED_WIDTH : EXPANDED_WIDTH)};
  margin: 8px;
  height: calc(100vh - 16px);
  background-color: #1a9187; /* teal */
  color: #ffffff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.25s ease;
`;

/* small white button sitting on the right edge, like the screenshot */
export const ToggleButton = styled.button`
  position: absolute;
  top: 22px;
  right: -12px;
  width: 24px;
  height: 24px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  color: #1f2937;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  cursor: pointer;

  &:hover {
    color: #14b8a6;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

export const LogoArea = styled.div<{ $collapsed: boolean }>`
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: ${({ $collapsed }) => ($collapsed ? "center" : "flex-start")};
  padding: ${({ $collapsed }) => ($collapsed ? "0" : "0 20px")};
  margin-bottom: 8px;
  overflow: hidden;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);

  svg {
    flex-shrink: 0;
  }
`;

export const LogoText = styled.div`
  margin-left: 12px;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  .logo-title {
    font-weight: 700;
    font-size: 14px;
    line-height: 1;
  }

  .logo-sub {
    font-size: 10px;
    margin-top: 3px;
    color: rgba(255, 255, 255, 0.75);
  }
`;

export const NavMenu = styled.nav`
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 8px;
  overflow-x: hidden;
  overflow-y: auto;
`;

export const StyledNavLink = styled(NavLink)<{ $collapsed: boolean }>`
  position: relative;
  display: flex;
  align-items: center;
  justify-content: ${({ $collapsed }) => ($collapsed ? "center" : "flex-start")};
  gap: ${({ $collapsed }) => ($collapsed ? "0" : "12px")};
  height: 42px;
  padding: ${({ $collapsed }) => ($collapsed ? "0" : "0 14px")};
  text-decoration: none;
  color: rgba(255, 255, 255, 0.85);
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
  transition: background-color 0.2s ease, color 0.2s ease;

  &:hover {
    background-color: rgba(255, 255, 255, 0.12);
    color: #ffffff;
  }

  /* React Router adds the 'active' class to the current route */
  &.active {
    background-color: #14b8a6;
    color: #ffffff;
  }

  /* white indicator bar on the left edge of the active item */
  &.active::before {
    content: "";
    position: absolute;
    left: -8px;
    top: 6px;
    bottom: 6px;
    width: 4px;
    border-radius: 0 4px 4px 0;
    background: #ffffff;
  }

  svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  .nav-label {
    display: ${({ $collapsed }) => ($collapsed ? "none" : "inline")};
    overflow: hidden;
    text-overflow: ellipsis;
  }
`;