// Mirrors the backend password policy (app/utils/validators.py) so users see problems early.
// The server still enforces the rule on every request.

export function passwordProblems(value) {
  const problems = []
  if (!value || value.length < 10) problems.push('at least 10 characters')
  if (value && value.length > 128) problems.push('at most 128 characters')
  if (!/[A-Z]/.test(value || '')) problems.push('an uppercase letter')
  if (!/[a-z]/.test(value || '')) problems.push('a lowercase letter')
  if (!/[0-9]/.test(value || '')) problems.push('a digit')
  if (!/[^A-Za-z0-9]/.test(value || '')) problems.push('a symbol')
  return problems
}

/** Ant Design form rule for new passwords. */
export const passwordRule = {
  validator(_rule, value) {
    const problems = passwordProblems(value)
    return problems.length
      ? Promise.reject(new Error(`Password needs ${problems.join(', ')}`))
      : Promise.resolve()
  },
}

/** Ant Design form rule: must match another field. */
export function matchesField(field, message = 'The passwords do not match') {
  return ({ getFieldValue }) => ({
    validator(_rule, value) {
      return !value || getFieldValue(field) === value
        ? Promise.resolve()
        : Promise.reject(new Error(message))
    },
  })
}

export const PASSWORD_HINT =
  'At least 10 characters with an uppercase letter, a lowercase letter, a digit and a symbol.'
