import { Outlet, useLocation } from "react-router-dom";
import { MainLayoutWrapper, RightColumn, MainContent } from "./style";
import Header from "../header/Header";
import Sidebar from "../sidebar/Sidebar";
import ScreenErrorBoundary from "../base/feedback/ScreenErrorBoundary";

const MainLayout = () => {
  const { pathname } = useLocation();
  return (
    <MainLayoutWrapper>
      <Sidebar />
      <RightColumn>
        <Header />
        <MainContent>
          {/* the current screen; a crash in it stays inside it */}
          <ScreenErrorBoundary key={pathname}>
            <Outlet />
          </ScreenErrorBoundary>
        </MainContent>
      </RightColumn>
    </MainLayoutWrapper>
  );
};

export default MainLayout;
