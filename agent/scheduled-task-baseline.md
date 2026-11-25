# Scheduled task: hourly baseline check (part 2)

Create it in the SRE Agent portal: **Automation > Create > Scheduled task**. Keep the agent autonomy level on **Review**.

**Name:** baseline-check

**Schedule:** hourly, at minute 45 (so a proposal lands before the next hour starts)

**Instructions:**

> For every container app in resource group `<your-rg>` tagged `aiops-managed=true`:
> 1. Read the `aiops-*` tags. The envelope is `aiops-min-replicas` to `aiops-max-replicas`.
> 2. Get the `Replicas` (Maximum) and `Requests` (Total) platform metrics at 1-hour grain for the last 28 days and
>    work out the median for the coming hour-of-week.
> 3. If the median replica count for the coming hour is higher than the app's current minReplicas, propose raising
>    minReplicas to that value for the peak, clipped to the envelope. If it is lower and the app is above the floor,
>    propose lowering it.
> 4. Never propose values outside the envelope and never change maxReplicas above `aiops-max-replicas`.
> 5. Report what you looked at, the numbers, and the exact change you propose.

In part 4 step 2 and 3 become one call to the MCP tool `get_baseline`, and the change becomes `set_scale_range`.
