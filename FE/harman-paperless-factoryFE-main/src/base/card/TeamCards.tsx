import { IconButton } from "@mui/material";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import type { Team } from "../../constants/types";
import { AvatarStack, InitialsAvatar } from "../avatar";

interface Props {
  team: Team;
  onOpen: (team: Team) => void;
}

const TeamCard = ({ team, onOpen }: Props) => (
  <div className="team-card">
    <div className="team-card-top">
      <InitialsAvatar initials={team.code} size={46} />
      <div>
        <div className="team-name">{team.name}</div>
        <div className="team-members">
          {team.members} {team.members === 1 ? "member" : "members"}
        </div>
      </div>
    </div>
    <div className="team-card-bottom">
      <AvatarStack
        initials={team.memberInitials}
        extra={team.members > team.memberInitials.length ? `+${team.members - team.memberInitials.length}` : undefined}
      />
      <IconButton className="open-team-btn" size="small" aria-label={`Open ${team.name}`} onClick={() => onOpen(team)}>
        <ArrowForwardIcon fontSize="small" />
      </IconButton>
    </div>
  </div>
);

export default TeamCard;