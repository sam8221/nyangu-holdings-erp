import dayjs from 'dayjs'

/** dayjs (from a DatePicker) -> "YYYY-MM-DD" for the API. */
export const toApiDate = (value) => (value ? dayjs(value).format('YYYY-MM-DD') : null)

/** "YYYY-MM-DD" from the API -> dayjs for a DatePicker. */
export const fromApiDate = (value) => (value ? dayjs(value) : null)

export const today = () => dayjs()
