/**
 * Authentication Context for Gatekeeper
 *
 * Manages user authentication state, login/logout functions,
 * and provides protected route functionality.
 */

import React, { createContext, useContext, useState, useEffect } from "react";
import api from "../services/api";

const AuthContext = createContext(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  /**
   * Check if user has a valid token on mount
   * Skip verification for Sentry OAuth callback (no auth required)
   */
  useEffect(() => {
    const checkAuth = async () => {
      // Skip auth check for Sentry callback (public route)
      if (window.location.pathname === "/auth/sentry/callback") {
        console.log("[AuthContext] Skipping auth check for Sentry callback");
        setLoading(false);
        return;
      }

      console.log("[AuthContext] Checking auth for path:", window.location.pathname);
      const token = localStorage.getItem("access_token");
      const storedUser = localStorage.getItem("user");

      console.log("[AuthContext] Token exists:", !!token, "User exists:", !!storedUser);
      console.log("[AuthContext] isAuthenticated before check:", isAuthenticated);

      if (token && storedUser) {
        try {
          // Verify token is still valid
          console.log("[AuthContext] Verifying token...");
          await api.verifyToken(token);
          setUser(JSON.parse(storedUser));
          setIsAuthenticated(true);
          console.log("[AuthContext] Token verified successfully");
        } catch (error) {
          // Token invalid, clear storage
          console.error("[AuthContext] Token verification failed:", error);
          console.error("[AuthContext] Clearing localStorage and redirecting to login");
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          localStorage.removeItem("user");
          setIsAuthenticated(false);
        }
      }
      setLoading(false);
    };

    checkAuth();
  }, []);

  /**
   * Initiate GitLab OAuth flow
   */
  const login = async () => {
    try {
      const response = await api.initiateGitLabOAuth();
      // Redirect to GitLab OAuth page
      window.location.href = response.oauth_url;
    } catch (error) {
      console.error("Login failed:", error);
      throw error;
    }
  };

  /**
   * Handle OAuth callback and store tokens
   */
  const handleCallback = async (code, state) => {
    try {
      const response = await api.handleOAuthCallback(code, state);

      // Store tokens
      localStorage.setItem("access_token", response.access_token);
      if (response.refresh_token) {
        localStorage.setItem("refresh_token", response.refresh_token);
      }
      localStorage.setItem("user", JSON.stringify(response.user));

      // Update state
      setUser(response.user);
      setIsAuthenticated(true);

      return response.user;
    } catch (error) {
      console.error("OAuth callback failed:", error);
      throw error;
    }
  };

  /**
   * Logout user and clear session
   */
  const logout = async () => {
    const token = localStorage.getItem("access_token");
    try {
      if (token) {
        await api.logout(token);
      }
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      // Clear local storage regardless of API call success
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      localStorage.removeItem("user");
      setUser(null);
      setIsAuthenticated(false);
      // Redirect to login
      window.location.href = "/login";
    }
  };

  /**
   * Update user information
   */
  const updateUser = (newUserData) => {
    const updatedUser = { ...user, ...newUserData };
    setUser(updatedUser);
    localStorage.setItem("user", JSON.stringify(updatedUser));
  };

  const value = {
    user,
    loading,
    isAuthenticated,
    login,
    logout,
    handleCallback,
    updateUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

/**
 * Protected Route Component
 *
 * Wraps routes that require authentication.
 * Redirects to login if user is not authenticated.
 */
export const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F2F4F7]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#FC6D26]"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    window.location.href = "/login";
    return null;
  }

  return children;
};

export default AuthContext;
