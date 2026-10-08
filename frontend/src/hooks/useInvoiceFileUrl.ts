import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getInvoiceFileBlob } from "@/services/invoices";

/** Récupère le fichier source (protégé par JWT) en Blob puis expose une
 * URL objet locale utilisable dans <img>/<iframe>. Révoque l'URL à chaque
 * changement pour éviter les fuites mémoire. */
export function useInvoiceFileUrl(invoiceId: number, enabled = true) {
  const blobQuery = useQuery({
    queryKey: ["invoice-file", invoiceId],
    queryFn: () => getInvoiceFileBlob(invoiceId),
    enabled,
  });
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!blobQuery.data) return;
    const url = URL.createObjectURL(blobQuery.data);
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [blobQuery.data]);

  return { url: objectUrl, isLoading: blobQuery.isLoading, isError: blobQuery.isError };
}
