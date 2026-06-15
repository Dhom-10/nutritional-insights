import pandas as pd

# Optimized read: load only needed columns to reduce memory and speed up processing
needed_columns = ['Diet_type', 'Recipe_name', 'Cuisine_type', 'Protein(g)', 'Carbs(g)', 'Fat(g)']
df = pd.read_csv('All_Diets.csv', usecols=needed_columns)

# ---- Clean data: handle missing values ----
# Fill any missing protein, carbs, or fat with the column average
for col in ['Protein(g)', 'Carbs(g)', 'Fat(g)']:
    df[col] = df[col].fillna(df[col].mean())

# ---- 1. Average macronutrients for each diet type ----
avg_macros = df.groupby('Diet_type')[['Protein(g)', 'Carbs(g)', 'Fat(g)']].mean()
print("Average macronutrients by diet type:")
print(avg_macros)

# ---- 2. Top 5 protein-rich recipes for each diet type ----
top_protein = df.sort_values('Protein(g)', ascending=False).groupby('Diet_type').head(5)
print("\nTop 5 protein-rich recipes per diet type:")
print(top_protein[['Diet_type', 'Recipe_name', 'Protein(g)']])

# ---- 3. Diet type with highest protein content ----
highest_protein_diet = avg_macros['Protein(g)'].idxmax()
print("\nDiet type with highest average protein:")
print(highest_protein_diet)

# ---- 4. Most common cuisine for each diet type ----
common_cuisine = df.groupby('Diet_type')['Cuisine_type'].agg(lambda x: x.mode()[0])
print("\nMost common cuisine per diet type:")
print(common_cuisine)

# ---- 5. New metrics: ratios ----
df['Protein_to_Carbs_ratio'] = df['Protein(g)'] / df['Carbs(g)']
df['Carbs_to_Fat_ratio'] = df['Carbs(g)'] / df['Fat(g)']
print("\nSample of new ratio columns:")
print(df[['Recipe_name', 'Protein_to_Carbs_ratio', 'Carbs_to_Fat_ratio']].head())

# ==================================================
# VISUALIZATIONS
# ==================================================
import matplotlib.pyplot as plt
import seaborn as sns

# ---- 1. Bar chart: average protein by diet type ----
plt.figure(figsize=(8, 5))
sns.barplot(x=avg_macros.index, y=avg_macros['Protein(g)'])
plt.title('Average Protein by Diet Type')
plt.xlabel('Diet Type')
plt.ylabel('Average Protein (g)')
plt.tight_layout()
plt.savefig('bar_chart_protein.png')

# ---- 2. Heatmap: macronutrients by diet type ----
plt.figure(figsize=(8, 5))
sns.heatmap(avg_macros, annot=True, fmt='.1f', cmap='YlOrRd')
plt.title('Average Macronutrients by Diet Type')
plt.tight_layout()
plt.savefig('heatmap_macros.png')


# ---- 3. Scatter plot: top 5 protein recipes across cuisines ----
plt.figure(figsize=(10, 6))
sns.scatterplot(data=top_protein, x='Cuisine_type', y='Protein(g)', hue='Diet_type', s=100)
plt.title('Top 5 Protein-Rich Recipes Across Cuisines')
plt.xlabel('Cuisine Type')
plt.ylabel('Protein (g)')
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig('scatter_protein.png')

print("\nAll charts saved as PNG files.")