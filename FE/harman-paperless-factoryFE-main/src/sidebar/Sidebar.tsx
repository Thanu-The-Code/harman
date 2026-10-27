import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Tooltip } from "@mui/material";
import {
  LogoArea,
  LogoText,
  NavMenu,
  SidebarContainer,
  StyledNavLink,
  ToggleButton,
} from "./style";
import { SidebarMenuIcons } from "../assets";
import { useMeQuery } from "../api/auth.api";

const {
  activity_log,
  change_request,
  dashboard,
  doc_repo,
  my_approvals,
  my_documents,
  people_teams,
  resource_librarry,
  template_builder,
  template_repo,
} = SidebarMenuIcons;

const navItems = [
  {
    path: "/",
    name: "Dashboard",
    icon: <img src={dashboard} alt="" />,
  },
  {
    path: "/resources",
    name: "Resources Library",
    icon: <img src={resource_librarry} alt="" />,
  },
  {
    path: "/my-forms",
    name: "My Documents",
    icon: <img src={my_documents} alt="" />,
  },
  {
    // approvers (CFT, QMS Coordinator) need their queue one click away, not only via the bell
    path: "/my-approvals",
    name: "My Approvals",
    icon: <img src={my_approvals} alt="" />,
  },

  {
    path: "/doc-repo",
    name: "Doc Repository",
    icon: <img src={doc_repo} alt="" />,
  },

  {
    path: "/builder",
    adminOnly: true,
    name: "Template Builder",
    icon: <img src={template_builder} alt="" />,
  },

  {
    path: "/builder-repo",
    adminOnly: true,
    name: "Template Repo",
    icon: <img src={template_repo} alt="" />,
  },

  {
    path: "/request",
    name: "Change Request",
    icon: <img src={change_request} alt="" />,
  },

  {
    path: "/people-teams",
    adminOnly: true,
    name: "Roles & Permissions",
    icon: <img src={people_teams} alt="" />,
  },
  {
    path: "/activity-log",
    name: "Activity Log",
    icon: <img src={activity_log} alt="" />,
  },
];

const STORAGE_KEY = "sidebar-collapsed";

const readInitial = (): boolean => {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
};

const Sidebar = () => {
  const [saved, setCollapsed] = useState<boolean>(readInitial);
  // the template designer needs the width: there the menu starts folded, without changing the saved choice
  const onDesigner = /^\/builder\/[^/]+\/build$/.test(useLocation().pathname);
  const [designerOpen, setDesignerOpen] = useState(false);
  const collapsed = onDesigner ? !designerOpen : saved;
  const { data: me } = useMeQuery();
  // template authoring and people management are admin-only in the API
  const visibleItems = navItems.filter((item) => !item.adminOnly || me?.is_admin);

  const toggle = () =>
    onDesigner
      ? setDesignerOpen((open) => !open)
      : setCollapsed((prev) => {
          const next = !prev;
          try {
            localStorage.setItem(STORAGE_KEY, String(next));
          } catch {
            /* ignore */
          }
          return next;
        });

  return (
    <SidebarContainer $collapsed={collapsed}>
      <ToggleButton
        type="button"
        onClick={toggle}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        aria-expanded={!collapsed}
      >
        {/* » when collapsed, « when expanded */}
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {collapsed ? (
            <path d="M6 17l5-5-5-5M13 17l5-5-5-5" />
          ) : (
            <path d="M18 17l-5-5 5-5M11 17l-5-5 5-5" />
          )}
        </svg>
      </ToggleButton>

      <LogoArea $collapsed={collapsed}>
        {/* Replace with your actual Logo SVG or Image */}
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#ffffff"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
        </svg>
        {!collapsed && (
          <LogoText>
            <div className="logo-title">Paperless Factory</div>
            <div className="logo-sub">QUALITY RECORDS</div>
          </LogoText>
        )}
      </LogoArea>

      <NavMenu>
        {visibleItems.map((item) => (
          <Tooltip
            key={item.path}
            title={collapsed ? item.name : ""}
            placement="right"
            arrow
          >
            <StyledNavLink
              to={item.path}
              end={item.path === "/"}
              $collapsed={collapsed}
              aria-label={item.name}
            >
              {item.icon}
              <span className="nav-label">{item.name}</span>
            </StyledNavLink>
          </Tooltip>
        ))}
      </NavMenu>
    </SidebarContainer>
  );
};

export default Sidebar;
