/**
 * Shared validation utilities for auth forms.
 * 
 * These rules MUST match backend validators in:
 * - backend/schemas.py (RegisterRequest, ResetPasswordRequest)
 */

export interface ValidationResult {
  valid: boolean;
  error: string | null;
}

/**
 * Validate password complexity.
 * Must match backend RegisterRequest and ResetPasswordRequest validators.
 */
export function validatePassword(password: string): ValidationResult {
  if (password.length < 8) {
    return { valid: false, error: 'Password must be at least 8 characters.' };
  }
  if (!/[a-z]/.test(password)) {
    return { valid: false, error: 'Password must include at least one lowercase letter.' };
  }
  if (!/[A-Z]/.test(password)) {
    return { valid: false, error: 'Password must include at least one uppercase letter.' };
  }
  if (!/\d/.test(password)) {
    return { valid: false, error: 'Password must include at least one digit.' };
  }
  if (!/[!@#$%^&*()\-_=+\[\]{};:,.?/]/.test(password)) {
    return { valid: false, error: 'Password must include at least one special character (!@#$%^&*…).' };
  }
  return { valid: true, error: null };
}

/**
 * Validate username.
 */
export function validateUsername(username: string): ValidationResult {
  if (username.length < 3) {
    return { valid: false, error: 'Username must be at least 3 characters.' };
  }
  return { valid: true, error: null };
}

/**
 * Validate email format.
 */
export function validateEmail(email: string): ValidationResult {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return { valid: false, error: 'Please enter a valid email address.' };
  }
  return { valid: true, error: null };
}
