## 检索式全文

以下由 `data/queries.json` 生成，勿手工编辑。

```text
A_metatrans_host
(metatranscriptomic*[tiab] OR metatranscriptom*[tiab]) AND (host[tiab] OR "host response"[tiab] OR "host gene"[tiab])

B_mngs_hostresp
("metagenomic next-generation sequencing"[tiab] OR mNGS[tiab] OR "metagenomic sequencing"[tiab] OR "metagenomics"[tiab]) AND ("host response"[tiab] OR "host gene expression"[tiab] OR "host transcriptom*"[tiab] OR "host RNA"[tiab])

C_csf_host
("cerebrospinal fluid"[tiab] OR CSF[tiab]) AND (transcriptom*[tiab] OR "host response"[tiab] OR "gene expression"[tiab] OR "RNA-seq"[tiab] OR "RNA sequencing"[tiab])

D_septicyte_genes
(SeptiCyte[tiab] OR CEACAM4[tiab] OR PLAC8[tiab] OR PLA2G7[tiab] OR "LAMP1"[tiab])

E_medmed_markers
(MeMed[tiab] OR TRAIL[tiab] OR TNFSF10[tiab] OR "IP-10"[tiab] OR CXCL10[tiab] OR MX1[tiab]) AND (infection[tiab] OR sepsis[tiab] OR "host response"[tiab] OR viral[tiab])

F_pmseq
(PMseq[tiab] OR "PM-seq"[tiab] OR "PMSEQ"[tiab])

G_cns_infect_tx
(meningit*[tiab] OR encephalit*[tiab] OR "central nervous system infection*"[tiab] OR "CNS infection*"[tiab]) AND (transcriptom*[tiab] OR "RNA-seq"[tiab] OR "RNA sequencing"[tiab] OR "gene expression"[tiab])

H_dualrnaseq
("dual RNA-seq"[tiab] OR "dual RNA sequencing"[tiab] OR "dual transcriptom*"[tiab])

I_hostdepletion
("host depletion"[tiab] OR "host read removal"[tiab] OR "rRNA depletion"[tiab] OR "ribosomal RNA depletion"[tiab]) AND (sequencing[tiab] OR metagenom*[tiab] OR transcriptom*[tiab])

J_sepsis_hostsig
(sepsis[tiab] OR septic[tiab]) AND ("host response"[tiab] OR "host transcriptom*"[tiab] OR "gene expression signature"[tiab] OR "transcriptomic signature"[tiab]) AND (diagnos*[tiab] OR biomarker*[tiab] OR classif*[tiab])

K_csf_mngs_clin
("cerebrospinal fluid"[tiab] OR CSF[tiab]) AND (mNGS[tiab] OR "metagenomic next-generation sequencing"[tiab] OR metatranscriptom*[tiab]) AND (infection[tiab] OR meningitis[tiab] OR encephalitis[tiab])

L_longread_mt
(nanopore[tiab] OR "long-read"[tiab] OR "Oxford Nanopore"[tiab]) AND (metatranscriptom*[tiab] OR "metagenomic sequencing"[tiab] OR mNGS[tiab])

M_tbm_host
(tuberculous meningitis[tiab] OR "TB meningitis"[tiab] OR "tuberculosis meningitis"[tiab]) AND (transcriptom*[tiab] OR "host response"[tiab] OR "gene expression"[tiab] OR RNA[tiab])

N_hostmrna_quant
("host mRNA"[tiab] OR "human mRNA"[tiab] OR "host transcript"[tiab]) AND (quantif*[tiab] OR abundanc*[tiab] OR "expression profile"[tiab] OR "read counts"[tiab])

O_hostresp_assay
("host response assay*"[tiab] OR "host response test*"[tiab] OR "host-response assay*"[tiab] OR "host response signature*"[tiab] OR "host transcriptomic assay*"[tiab])

P_septicyte_all
(SeptiCyte[tiab] OR SeptiScore[tiab] OR "MeMed BV"[tiab] OR FebriDx[tiab] OR "Immunexpress"[tiab] OR "host response panel*"[tiab])

Q_hostreads
("host reads"[tiab] OR "host sequences"[tiab] OR "human reads"[tiab] OR "non-pathogen reads"[tiab] OR "host-derived reads"[tiab] OR "host reads removal"[tiab])

R_hosttx_meta
("host transcriptom*"[tiab] OR "host gene expression"[tiab] OR "human transcriptom*"[tiab]) AND (metagenom*[tiab] OR metatranscriptom*[tiab] OR mNGS[tiab] OR "next-generation sequencing"[tiab])

S_clinicalmeta_host
("clinical metagenomics"[tiab] OR "clinical metagenomic"[tiab] OR "diagnostic metagenomic"[tiab] OR "metagenomic data"[tiab]) AND (host[tiab] OR human[tiab] OR transcriptom*[tiab] OR "RNA"[tiab])

T_csf_rnaseq_inf
("cerebrospinal fluid"[tiab] OR CSF[tiab] OR mening*[tiab] OR encephal*[tiab]) AND ("RNA sequencing"[tiab] OR "RNA-seq"[tiab] OR "transcriptomic profiling"[tiab] OR "transcriptome profiling"[tiab]) AND (infection[tiab] OR infectious[tiab] OR pathogen*[tiab] OR host[tiab] OR immune[tiab])

U_hostvsmicrobe
(host[tiab] AND (microb*[tiab] OR bacteri*[tiab] OR pathogen*[tiab])) AND (separat*[tiab] OR discriminat*[tiab] OR deplet*[tiab] OR classif*[tiab] OR differentiat*[tiab] OR benchmark*[tiab]) AND (transcriptom*[tiab] OR metatranscriptom*[tiab] OR "RNA-seq"[tiab] OR sequencing[tiab])

V_classifier_stability
(transcriptom*[tiab] OR "gene expression"[tiab] OR "expression signature*"[tiab]) AND (classifier*[tiab] OR "machine learning"[tiab] OR "diagnostic model"[tiab] OR signature*[tiab]) AND ("batch effect*"[tiab] OR preprocessing[tiab] OR "external validation"[tiab] OR reproducibility[tiab] OR "cross-platform"[tiab] OR "cross-cohort"[tiab] OR overfit*[tiab] OR "decision curve"[tiab] OR benchmark*[tiab]) AND (infection[tiab] OR sepsis[tiab] OR "host response"[tiab] OR "host transcriptom*"[tiab])

W_csf_hostmarker
(meningit*[tiab] OR encephalit*[tiab] OR "central nervous system infection*"[tiab] OR "CNS infection*"[tiab]) AND ("cerebrospinal fluid"[tiab] OR CSF[tiab]) AND ("host response"[tiab] OR proteom*[tiab] OR transcriptom*[tiab] OR "immune mediator*"[tiab] OR "host biomarker*"[tiab] OR "host gene"[tiab])

```
