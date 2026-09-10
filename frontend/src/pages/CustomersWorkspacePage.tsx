import CustomerValueClassifications from "../components/CustomerValueClassifications";
import CustomersPage from "./CustomersPage";

interface Props {
  canWrite: boolean;
  storeId: number;
}

export default function CustomersWorkspacePage({ canWrite, storeId }: Props) {
  return (
    <>
      {storeId > 0 && <CustomerValueClassifications storeId={storeId} />}
      <CustomersPage canWrite={canWrite} storeId={storeId} />
    </>
  );
}
