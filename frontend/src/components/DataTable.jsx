import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Alert, Button, Card, Input, Table } from 'antd'
import { errorMessage } from '../api/errors'

const ORDER_TO_API = { ascend: 'asc', descend: 'desc' }
const ORDER_FROM_API = { asc: 'ascend', desc: 'descend' }

/**
 * A server-driven table: paging, sorting and search are done by the API.
 *
 * - `fetcher(params)` receives { page, page_size, search, sort_by, sort_order, ...filters }
 *   and must return { items, meta }.
 * - Columns that set `sortField` become sortable by that API sort field.
 * - Changing `filters` sends the table back to page 1.
 */
export default function DataTable({
  queryKey,
  fetcher,
  columns,
  filters = {},
  toolbar,
  searchPlaceholder = 'Search',
  defaultSort,
  rowKey = 'id',
  searchable = true,
}) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [sort, setSort] = useState(defaultSort || {})
  const [search, setSearch] = useState('')

  // Reset to page 1 when the filters change (adjusting state during render, not in an effect).
  const filtersKey = JSON.stringify(filters)
  const [previousFilters, setPreviousFilters] = useState(filtersKey)
  if (filtersKey !== previousFilters) {
    setPreviousFilters(filtersKey)
    setPage(1)
  }

  const params = {
    page,
    page_size: pageSize,
    search: search || undefined,
    sort_by: sort.field,
    sort_order: sort.order,
    ...filters,
  }
  const query = useQuery({
    queryKey: [...queryKey, params],
    queryFn: () => fetcher(params),
    placeholderData: keepPreviousData,
  })

  const tableColumns = columns.map((column) =>
    column.sortField
      ? {
          ...column,
          sorter: true,
          sortOrder: sort.field === column.sortField ? ORDER_FROM_API[sort.order] || null : null,
        }
      : column,
  )

  const handleChange = (pagination, _filters, sorter) => {
    const single = Array.isArray(sorter) ? sorter[0] : sorter
    const column = single?.column
    if (column?.sortField && single.order) {
      setSort({ field: column.sortField, order: ORDER_TO_API[single.order] })
    } else {
      setSort(defaultSort || {})
    }
    if (pagination.pageSize !== pageSize) {
      setPageSize(pagination.pageSize)
      setPage(1)
    } else {
      setPage(pagination.current)
    }
  }

  return (
    <Card styles={{ body: { padding: 16 } }}>
      <div className="page-toolbar">
        {searchable && (
          <Input.Search
            allowClear
            placeholder={searchPlaceholder}
            style={{ width: 280 }}
            onSearch={(value) => {
              setSearch(value.trim())
              setPage(1)
            }}
          />
        )}
        {toolbar}
      </div>
      {query.isError && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message={errorMessage(query.error)}
          action={
            <Button size="small" onClick={() => query.refetch()}>
              Retry
            </Button>
          }
        />
      )}
      <Table
        rowKey={rowKey}
        columns={tableColumns}
        dataSource={query.data?.items || []}
        loading={query.isFetching}
        onChange={handleChange}
        scroll={{ x: 'max-content' }}
        pagination={{
          current: page,
          pageSize,
          total: query.data?.meta?.total || 0,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (total) => `${total} record${total === 1 ? '' : 's'}`,
        }}
      />
    </Card>
  )
}
