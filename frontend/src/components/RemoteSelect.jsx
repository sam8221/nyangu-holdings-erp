import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Select, Spin } from 'antd'

/**
 * A searchable Select whose options come from a paginated list endpoint.
 *
 * - `fetcher(params)` is a list call such as customersApi.list
 * - `labelOf(item)` builds the option text
 * - `selected` (optional) is the currently chosen record(s), so the label shows even when that
 *   record is not in the current search results (e.g. when editing)
 * - `extraParams` are sent with every search (e.g. { is_active: true })
 */
export default function RemoteSelect({
  queryKey,
  fetcher,
  labelOf,
  selected,
  extraParams = {},
  pageSize = 50,
  ...selectProps
}) {
  const [search, setSearch] = useState('')
  const [debounced, setDebounced] = useState('')
  const timer = useRef(null)
  useEffect(() => () => clearTimeout(timer.current), [])

  const query = useQuery({
    queryKey: [...queryKey, 'options', debounced, extraParams],
    queryFn: () => fetcher({ page: 1, page_size: pageSize, search: debounced, ...extraParams }),
    staleTime: 60_000,
  })

  const options = useMemo(() => {
    const items = query.data?.items || query.data || []
    const byId = new Map(items.map((item) => [item.id, item]))
    for (const item of [].concat(selected || [])) {
      if (item?.id && !byId.has(item.id)) byId.set(item.id, item)
    }
    return [...byId.values()].map((item) => ({ value: item.id, label: labelOf(item) }))
  }, [query.data, selected, labelOf])

  const onSearch = (value) => {
    setSearch(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => setDebounced(value.trim()), 300)
  }

  return (
    <Select
      showSearch={{ filterOption: false, searchValue: search, onSearch }}
      allowClear
      options={options}
      notFoundContent={query.isFetching ? <Spin size="small" /> : 'No matches'}
      loading={query.isFetching}
      {...selectProps}
    />
  )
}
