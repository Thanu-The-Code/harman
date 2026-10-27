import styled from "styled-components";

export const StatsSummaryWrapper = styled.div`
  width: 100%;

  * {
    box-sizing: border-box;
  }

  .stats-summary-track {
    width: 100%;
    display: flex;
    align-items: stretch;
    gap: 16px;
  }

  /* one card per stat */
  .stats-summary-card {
    flex: 1;
    min-width: 0;
    padding: 10px 10px 8px;
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    box-shadow: 0px 2px 8px rgba(15, 23, 42, 0.05);
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .stats-summary-card.is-clickable {
    cursor: pointer;
    transition: box-shadow 0.2s ease, border-color 0.2s ease;
  }

  .stats-summary-card.is-clickable:hover {
    border-color: #14b8a6;
    box-shadow: 0px 4px 14px rgba(20, 184, 166, 0.15);
  }

  /* grey inner box: number on the left, illustration on the right */
  .stats-summary-top {
    position: relative;
    height: 60px;
    padding: 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
  }

  .stats-summary-value {
    color: #1f2937 !important;
    font-size: 24px !important;
    font-weight:600 !important;
    line-height: 1 !important;
  }

  .stats-summary-icon {
    position: absolute;
    right: 10px;
    top: 50%;
    transform: translateY(-50%);
    height: 47px;
    width: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;

    svg {
      width: 100%;
      height: 100%;
    }
  }

  .stats-summary-label {
    padding: 0 6px;
    color: #1f2937 !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    line-height: 1.3 !important;
    word-break: break-word;
  }

  @media (max-width: 900px) {
    .stats-summary-track {
      overflow-x: auto;
      overflow-y: hidden;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      padding-bottom: 4px;

      &::-webkit-scrollbar {
        display: none;
      }
    }

    .stats-summary-card {
      flex: 0 0 230px;
      min-width: 230px;
    }
  }

  @media (max-width: 480px) {
    .stats-summary-card {
      flex: 0 0 200px;
      min-width: 200px;
    }

    .stats-summary-value {
      font-size: 24px !important;
    }
  }
`;