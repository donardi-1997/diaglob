import CustomerValueClassifications from "../components/CustomerValueClassifications";
import SearchCustomerDetailOverlay from "../components/SearchCustomerDetailOverlay";
import CustomersPage from "./CustomersPage";

interface Props {
  canWrite: boolean;
  storeId: number;
  initialCustomerId?: number;
  searchRequestKey?: number;
}

export default function CustomersWorkspacePage({
  canWrite,
  storeId,
  initialCustomerId,
  searchRequestKey,
}: Props) {
  return (
    <>
      {storeId > 0 && <CustomerValueClassifications storeId={storeId} />}
      <CustomersPage canWrite={canWrite} storeId={storeId} />
      <SearchCustomerDetailOverlay
        customerId={initialCustomerId}
        storeId={storeId}
        requestKey={searchRequestKey}
      />
    </>
  );
}
