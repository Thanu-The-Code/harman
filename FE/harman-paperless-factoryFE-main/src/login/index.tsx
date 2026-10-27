import { useState, type FormEvent, type FC } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Box, Button, IconButton, Typography } from "@mui/material";
import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import VisibilityOffOutlinedIcon from "@mui/icons-material/VisibilityOffOutlined";
import { loginStyles } from "./style";
import { LoginImages } from "../assets";
import CustomTextField from "../base/dialog/CustomTextField";
import { useChangePasswordMutation, useLoginMutation } from "../api/auth.api";
import { api } from "../api/baseApi";
import { getApiErrorMessage } from "../api/errors";
import { getToken, setToken } from "../api/session";
import { useAppDispatch } from "../redux/store";

const { login_lfetImg, settings, ensureCompliance, goPaperless } = LoginImages;

const FEATURES = [
  {
    icon: goPaperless,
    title: "Go Paperless",
    text: "Reduce paperwork and save time",
  },
  {
    icon: settings,
    title: "Improve Efficiency",
    text: "Streamline form processes",
  },
  {
    icon: ensureCompliance,
    title: "Ensure Compliance",
    text: "Maintain accurate and secure records",
  },
];

const MIN_PASSWORD = 8;

const PasswordInput: FC<{
  label: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
}> = ({ label, placeholder, value, onChange }) => {
  const [show, setShow] = useState(false);
  return (
    <Box className="password-field-wrap">
      <CustomTextField
        className="login-field"
        label={label}
        placeholder={placeholder}
        type={show ? "text" : "password"}
        value={value}
        onChange={onChange}
      />
      <IconButton
        className="eye-btn"
        size="small"
        aria-label={show ? "Hide password" : "Show password"}
        onClick={() => setShow((s) => !s)}
        edge="end"
      >
        {show ? (
          <VisibilityOffOutlinedIcon fontSize="small" />
        ) : (
          <VisibilityOutlinedIcon fontSize="small" />
        )}
      </IconButton>
    </Box>
  );
};

const LoginPage: FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useAppDispatch();
  const [login, { isLoading: signingIn }] = useLoginMutation();
  const [changePassword, { isLoading: changing }] = useChangePasswordMutation();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [mustChange, setMustChange] = useState(false);
  const [formError, setFormError] = useState("");

  const query = new URLSearchParams(location.search);
  // a path of this app only ("/x", never "//elsewhere" or a full URL)
  const back = query.get("from");
  const from = (location.state as { from?: string } | null)?.from || (back && /^\/(?!\/)/.test(back) ? back : "/");
  const expired = query.get("expired") === "1";
  const goOn = () => navigate(from, { replace: true });

  // already signed in: nothing to do here
  if (getToken() && !mustChange) return <Navigate to={from} replace />;

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setFormError("Enter your username and password.");
      return;
    }

    setFormError("");
    try {
      const session = await login({ username: username.trim(), password }).unwrap();
      // nothing cached from an earlier account may leak into this one
      dispatch(api.util.resetApiState());
      setToken(session.access_token);
      if (session.must_change_password) {
        setMustChange(true);
        return;
      }
      goOn();
    } catch (error: unknown) {
      setFormError(
        (error as { status?: number })?.status === 401
          ? "Incorrect username or password."
          : getApiErrorMessage(error, "Login failed. Please try again."),
      );
    }
  };

  const handleChangePassword = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (newPassword.length < MIN_PASSWORD) {
      setFormError(`The new password needs at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (newPassword !== confirmPassword) {
      setFormError("The two new passwords do not match.");
      return;
    }
    setFormError("");
    try {
      await changePassword({ current_password: password, new_password: newPassword }).unwrap();
      goOn();
    } catch (error: unknown) {
      setFormError(getApiErrorMessage(error, "Could not change the password."));
    }
  };

  return (
    <Box className="login-page" sx={loginStyles}>
      <div className="login-layout">
        {/* left: illustration */}
        <section
          className="login-hero"
          style={{ backgroundImage: `url(${login_lfetImg})` }}
        >
          <div>
            <Typography className="hero-title">
              Digitize <span>Quality Records</span>
            </Typography>
            <Typography className="hero-subtitle">
              Create, manage and track forms effortlessly for a paperless and
              more efficient factory.
            </Typography>
          </div>

          <div className="hero-features">
            {FEATURES.map((f) => (
              <div className="hero-feature" key={f.title}>
                <img src={f.icon} alt="" className="feature-icon" />
                <div>
                  <div className="feature-title">{f.title}</div>
                  <div className="feature-text">{f.text}</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* right: form */}
        <section className="login-form-side">
          <div className="login-card">
            <div className="brand">
              <h1 className="brand-name">Paperless Factory</h1>
              <p className="brand-sub">A Harman Product</p>
            </div>

            {mustChange ? (
              <>
                <h2 className="login-heading">Set a new password</h2>
                <form className="login-form" onSubmit={handleChangePassword} noValidate>
                  <PasswordInput
                    label="New password"
                    placeholder={`At least ${MIN_PASSWORD} characters`}
                    value={newPassword}
                    onChange={setNewPassword}
                  />
                  <PasswordInput
                    label="Confirm new password"
                    placeholder="Type it again"
                    value={confirmPassword}
                    onChange={setConfirmPassword}
                  />
                  {formError && (
                    <p className="login-error" role="alert">
                      {formError}
                    </p>
                  )}
                  <Button
                    className="login-btn"
                    type="submit"
                    variant="contained"
                    disabled={changing}
                    fullWidth
                  >
                    Save and continue
                  </Button>
                </form>
              </>
            ) : (
              <>
                <h2 className="login-heading">Login</h2>
                {expired && (
                  <p className="login-notice" role="status">
                    Your sign-in has ended. Sign in again to carry on where you were.
                  </p>
                )}
                <form className="login-form" onSubmit={handleSubmit} noValidate>
                  <CustomTextField
                    className="login-field"
                    label="Username"
                    placeholder="Enter username or email"
                    value={username}
                    onChange={setUsername}
                  />
                  <PasswordInput
                    label="Password"
                    placeholder="Enter your password"
                    value={password}
                    onChange={setPassword}
                  />
                  {formError && (
                    <p className="login-error" role="alert">
                      {formError}
                    </p>
                  )}
                  <Button
                    className="login-btn"
                    type="submit"
                    variant="contained"
                    disabled={signingIn}
                    fullWidth
                  >
                    {signingIn ? "Logging in…" : "Log In"}
                  </Button>
                </form>
              </>
            )}

            <p className="login-footer">
              © 2026 Paperless Factory Platform. All rights reserved.
            </p>
          </div>
        </section>
      </div>
    </Box>
  );
};

export default LoginPage;
