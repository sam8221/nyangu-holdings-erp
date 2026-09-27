import { Button, Result } from 'antd'
import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <Result
      status="404"
      title="Page not found"
      subTitle="The page you are looking for does not exist."
      extra={
        <Link to="/">
          <Button type="primary">Go to the dashboard</Button>
        </Link>
      }
    />
  )
}
